"""The exhibit package's one network module: polite GETs of JSON from the Internet Archive's public
search API, for the Gap Hunt catalogue counts. Tests replace get_json and fail if anything reaches
a real host.

One retry rule: a timeout, a connection failure, a 5xx, 408 or 429 is tried again with backoff (a
Retry-After header is honored, up to MAX_WAIT_S); any other 4xx raises at once. Requests are made
one at a time with a pause between them, under a user agent that names the project and a contact."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

USER_AGENT = "archive-argues-exhibit/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ATTEMPTS = 4
MAX_WAIT_S = 60.0
PAUSE_S = 1.2


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def _retryable(status: int) -> bool:
    return status in (408, 429) or status >= 500


def get_json(url: str, params: dict, *, timeout_s: float = 40.0, sleep: Callable[[float], None] = time.sleep) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        req = urllib.request.Request(full, headers={"user-agent": USER_AGENT, "accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            sleep(PAUSE_S)
            return body
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
