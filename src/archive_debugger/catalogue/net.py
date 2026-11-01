"""The catalogue package's one network module: polite GETs to archive.org. Tests replace get and
fail if anything reaches a real host.

One retry rule: a timeout, a connection failure, a 5xx, 408 or 429 is tried again with backoff (a
Retry-After header is honored, up to MAX_WAIT_S); any other 4xx raises at once. Repeated 429 or 503
responses are counted by the caller, which stops the whole fetch when they pile up (TooManyRefusals)
rather than pressing on."""
from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

USER_AGENT = "archive-argues-catalogue/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ATTEMPTS = 5
MAX_WAIT_S = 120.0
PAUSE_S = 0.5
MAX_CONCURRENCY = 2

_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)


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


def get(url: str, params: dict | None = None, *, timeout_s: float = 120.0, sleep: Callable[[float], None] = time.sleep,
        refusals: RefusalCounter | None = None) -> bytes:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    last: Exception | None = None
    with _slots:
        for attempt in range(ATTEMPTS):
            req = urllib.request.Request(full, headers={"user-agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    data = resp.read()
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
                last = HttpError(exc.code, text)
                wait = exc.headers.get("retry-after") if exc.headers else None
                delay = min(float(wait), MAX_WAIT_S) if wait and wait.replace(".", "", 1).isdigit() else 5.0 * 2 ** attempt
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                last = exc
                delay = 5.0 * 2 ** attempt
            if attempt < ATTEMPTS - 1:
                sleep(min(delay, MAX_WAIT_S))
    raise last if last else RuntimeError("request failed")
