"""The jobs package's one network module: JSON POSTs to model endpoints (Workers AI, a local Ollama
or an in-cluster vLLM server) and polite GETs of page images from archive.org. Tests replace these
functions and fail if anything reaches a real host.

One retry rule: a timeout, a connection failure, a 5xx, 408 or 429 is tried again with backoff (a
Retry-After header is honored, up to MAX_WAIT_S); any other 4xx raises at once."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Callable

USER_AGENT = "archive-argues-jobs/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ATTEMPTS = 5
MAX_WAIT_S = 60.0


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def _retryable(status: int) -> bool:
    return status in (408, 429) or status >= 500


def _request(req: urllib.request.Request, timeout_s: float, sleep: Callable[[float], None]) -> bytes:
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            if not _retryable(exc.code):
                raise HttpError(exc.code, text) from exc
            last = HttpError(exc.code, text)
            wait = exc.headers.get("retry-after") if exc.headers else None
            delay = min(float(wait), MAX_WAIT_S) if wait and wait.replace(".", "", 1).isdigit() else 2.0 * 2 ** attempt
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            last = exc
            delay = 2.0 * 2 ** attempt
        if attempt < ATTEMPTS - 1:
            sleep(delay)
    raise last if last else RuntimeError("request failed")


def post_json(url: str, headers: dict, body: dict, *, timeout_s: float = 300.0,
              sleep: Callable[[float], None] = time.sleep) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json", "user-agent": USER_AGENT, **headers})
    return json.loads(_request(req, timeout_s, sleep).decode("utf-8"))


def get_bytes(url: str, *, timeout_s: float = 60.0, sleep: Callable[[float], None] = time.sleep,
              pause_s: float = 1.0) -> bytes:
    req = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    data = _request(req, timeout_s, sleep)
    sleep(pause_s)                     # one request at a time, with a pause: polite to archive.org
    return data
