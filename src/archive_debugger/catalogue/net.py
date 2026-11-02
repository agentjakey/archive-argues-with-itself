"""The catalogue package's one network module: polite GETs to archive.org. Tests replace get and
fail if anything reaches a real host.

One retry rule: a timeout, a connection failure, a 5xx, 408 or 429 is tried again with backoff (a
Retry-After header is honored, up to MAX_WAIT_S); any other 4xx raises at once. Repeated 429 or 503
responses are counted by the caller, which stops the whole fetch when they pile up (TooManyRefusals)
rather than pressing on.

How many requests run at once is set by LIMIT (AdaptiveLimit). It starts at START_CONCURRENCY. It
rises one step, to at most MAX_CONCURRENCY, only after QUIET_S seconds at the current level with no
429, 503, other server error or connection failure, and with latency flat: the median time to the
first byte over the last LATENCY_WINDOW_S seconds is no more than LATENCY_RISE times the median at
the start of the level. Any of those errors puts it straight back to START_CONCURRENCY and restarts
the clock; so does latency that rises past the same bound after a step up. configure() sets the
start, the ceiling and the step for a run (the cloud fetch: 4, 8, 2); nothing may set a ceiling
above HARD_CEILING, the most requests the whole project ever sends archive.org at once."""
from __future__ import annotations

import socket
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

USER_AGENT = "archive-argues-catalogue/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ATTEMPTS = 5
MAX_WAIT_S = 120.0
PAUSE_S = 0.5
START_CONCURRENCY = 2
MAX_CONCURRENCY = 4
QUIET_S = 3600.0
LATENCY_WINDOW_S = 900.0
LATENCY_RISE = 1.25
MIN_SAMPLES = 50
HARD_CEILING = 8


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


class TooManyRefusals(Exception):
    """The server keeps answering 429 or 503: stop and report instead of pressing on."""


class RefusalCounter:
    def __init__(self, limit: int = 6):
        self.limit = limit
        self.count = 0
        self.lock = threading.Lock()

    def refused(self, status: int) -> None:
        with self.lock:
            self.count += 1
            if self.count >= self.limit:
                raise TooManyRefusals(f"{self.count} responses with 429 or 503 (last {status}): stopping the fetch")

    def ok(self) -> None:
        with self.lock:
            self.count = max(0, self.count - 1)


class AdaptiveLimit:
    """A concurrency limit that steps up only after a quiet hour with flat latency, and drops back
    to the start on any server error. `clock` is replaceable for tests."""

    def __init__(self, start: int = START_CONCURRENCY, ceiling: int = MAX_CONCURRENCY, quiet_s: float = QUIET_S,
                 window_s: float = LATENCY_WINDOW_S, rise: float = LATENCY_RISE, min_samples: int = MIN_SAMPLES,
                 clock: Callable[[], float] = time.monotonic, log: Optional[Callable[[str], None]] = None,
                 step: int = 1):
        if ceiling > HARD_CEILING or start > ceiling or start < 1 or step < 1:
            raise ValueError(f"concurrency must satisfy 1 <= start <= ceiling <= {HARD_CEILING} (got {start}, {ceiling})")
        self.start, self.ceiling, self.quiet_s, self.window_s = start, ceiling, quiet_s, window_s
        self.step = step
        self.rise, self.min_samples, self.clock, self.log = rise, min_samples, clock, log
        self.limit = start
        self.active = 0
        self.cond = threading.Condition()
        self.level_since = clock()
        self.last_problem: Optional[float] = None
        self.samples: list = []          # (time, seconds to first byte) at the current level
        self.baseline: Optional[float] = None
        self.hold_until = 0.0            # a Retry-After pauses every request, not just the refused one

    def acquire(self) -> None:
        with self.cond:
            while self.active >= self.limit or self.clock() < self.hold_until:
                wait = self.hold_until - self.clock()
                self.cond.wait(timeout=wait if wait > 0 else None)
            self.active += 1

    def hold(self, seconds: float) -> None:
        with self.cond:
            self.hold_until = max(self.hold_until, self.clock() + seconds)

    def release(self) -> None:
        with self.cond:
            self.active -= 1
            self.cond.notify_all()

    def _set(self, limit: int, why: str) -> None:
        if limit != self.limit and self.log:
            self.log(f"concurrency {self.limit} -> {limit}: {why}")
        self.limit = limit
        self.level_since = self.clock()
        self.samples = []
        self.baseline = None
        self.cond.notify_all()

    def problem(self, what: str) -> None:
        with self.cond:
            self.last_problem = self.clock()
            if self.limit != self.start or self.samples:
                self._set(self.start, what)

    def observe(self, ttfb_s: float) -> None:
        with self.cond:
            now = self.clock()
            self.samples.append((now, ttfb_s))
            early = [s for t, s in self.samples if t - self.level_since <= self.window_s]
            if self.baseline is None and len(early) >= self.min_samples and now - self.level_since > self.window_s:
                self.baseline = statistics.median(early)
            recent = [s for t, s in self.samples if now - t <= self.window_s]
            if self.baseline is None or len(recent) < self.min_samples:
                return
            flat = statistics.median(recent) <= self.rise * self.baseline
            if not flat and self.limit > self.start:
                self._set(self.start, f"latency rose ({statistics.median(recent):.2f}s against {self.baseline:.2f}s)")
                return
            quiet = now - self.level_since >= self.quiet_s and (self.last_problem is None or now - self.last_problem >= self.quiet_s)
            if flat and quiet and self.limit < self.ceiling:
                self._set(min(self.ceiling, self.limit + self.step),
                          f"{self.quiet_s / 3600:.0f} h with no server errors and flat latency")
            # keep the window bounded
            cutoff = now - max(self.quiet_s, self.window_s) - self.window_s
            if self.samples and self.samples[0][0] < cutoff:
                self.samples = [(t, s) for t, s in self.samples if t >= cutoff or t - self.level_since <= self.window_s]

    def state(self) -> dict:
        with self.cond:
            now = self.clock()
            return {"limit": self.limit, "level_for_s": round(now - self.level_since),
                    "since_problem_s": None if self.last_problem is None else round(now - self.last_problem),
                    "baseline_ttfb_s": None if self.baseline is None else round(self.baseline, 3)}


LIMIT = AdaptiveLimit()


def configure(start: int, ceiling: int, step: int = 1, log: Optional[Callable[[str], None]] = None) -> AdaptiveLimit:
    """Replace the module's limit for this process (before any request is sent)."""
    global LIMIT
    LIMIT = AdaptiveLimit(start=start, ceiling=ceiling, step=step, log=log)
    return LIMIT


def get(url: str, params: dict | None = None, *, timeout_s: float = 120.0, sleep: Callable[[float], None] = time.sleep,
        refusals: RefusalCounter | None = None, limit: AdaptiveLimit | None = None) -> bytes:
    limit = limit or LIMIT
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        req = urllib.request.Request(full, headers={"user-agent": USER_AGENT})
        limit.acquire()
        try:
            started = time.monotonic()
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                ttfb = time.monotonic() - started
                data = resp.read()
            limit.observe(ttfb)
            if refusals:
                refusals.ok()
            sleep(PAUSE_S)
            return data
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            if exc.code in (429, 503) and refusals:
                refusals.refused(exc.code)
            if not (exc.code in (408, 429) or exc.code >= 500):
                raise HttpError(exc.code, text) from exc
            limit.problem(f"HTTP {exc.code}")
            last = HttpError(exc.code, text)
            asked = retry_after_s(exc.headers.get("retry-after") if exc.headers else None)
            if asked is not None and asked > MAX_RETRY_AFTER_S:
                raise TooManyRefusals(f"HTTP {exc.code} with Retry-After {asked:.0f} s: stopping the fetch") from exc
            if asked is not None:
                limit.hold(asked)        # every request waits, as asked
            delay = asked if asked is not None else min(5.0 * 2 ** attempt, MAX_WAIT_S)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            limit.problem(type(exc).__name__)
            last = exc
            delay = min(5.0 * 2 ** attempt, MAX_WAIT_S)
        finally:
            limit.release()
        if attempt < ATTEMPTS - 1:
            sleep(delay)
    raise last if last else RuntimeError("request failed")


MAX_RETRY_AFTER_S = 3600.0


def retry_after_s(value: Optional[str]) -> Optional[float]:
    """Seconds from a Retry-After header: a number of seconds or an HTTP date; None when absent or unreadable."""
    if not value:
        return None
    value = value.strip()
    if value.replace(".", "", 1).isdigit():
        return float(value)
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        when = parsedate_to_datetime(value)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None
