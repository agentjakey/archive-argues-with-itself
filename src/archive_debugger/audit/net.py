"""The audit package's one network module for plain HTTP (the Workers AI judges). Tests replace
post_json and fail if anything reaches a real host.

One retry rule: a timeout, a connection failure, a 5xx, 408 or 429 is tried again with backoff (a
Retry-After header is honored, up to MAX_WAIT_S); any other 4xx raises at once."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Callable

USER_AGENT = "archive-argues-audit/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ATTEMPTS = 4
MAX_WAIT_S = 60.0
RETRY_STATUS = {408, 429}


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def _retryable(status: int) -> bool:
    return status in RETRY_STATUS or status >= 500


def post_json(url: str, headers: dict, body: dict, *, timeout_s: float = 120.0,
              sleep: Callable[[float], None] = time.sleep, response_headers: dict | None = None) -> dict:
    """The decoded JSON reply. When response_headers is given, the reply's headers are copied into
    it, with lower-case names."""
    data = json.dumps(body).encode("utf-8")
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": "application/json", "user-agent": USER_AGENT, **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if response_headers is not None:
                    response_headers.update({k.lower(): v for k, v in resp.headers.items()})
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
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
