"""The sources package's one network module, with a host allowlist.

A URL is fetched only when all of these hold: the scheme is https (or http, upgraded to https),
the host is on the allowlist exactly (no suffix tricks), there are no user credentials and no
explicit port, the host is a name and not an IP literal, and the name does not resolve to a
private, loopback, link-local or reserved address. Redirects are not followed automatically: each
Location is checked against the same rules before it is requested, at most MAX_REDIRECTS times.
Requests are polite (an identified user agent, one at a time, a pause, backoff) under the same
retry rule as every network module here. Tests replace resolve and opener and fail on any real host."""
from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

USER_AGENT = "archive-argues-sources/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
ALLOWED_HOSTS = frozenset({"web.archive.org", "archive.org"})
MAX_REDIRECTS = 5
MAX_BYTES = 8 * 1024 * 1024
ATTEMPTS = 4
PAUSE_S = 1.0


class Refused(Exception):
    """The URL is not one this project may fetch."""


class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


def resolve(host: str) -> list:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def check_url(url: str, *, allowed: frozenset = ALLOWED_HOSTS, resolver: Callable = resolve) -> str:
    """The URL to request (https), or Refused with the reason."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise Refused(f"scheme {parts.scheme!r} is not allowed")
    if parts.username or parts.password or "@" in parts.netloc:
        raise Refused("credentials in a URL are not allowed")
    if parts.port is not None:
        raise Refused("an explicit port is not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    try:
        ipaddress.ip_address(host.strip("[]"))
        raise Refused("an IP address is not allowed; hosts are named")
    except ValueError:
        pass
    if host not in allowed:
        raise Refused(f"host {host!r} is not on the allowlist")
    for addr in resolver(host):
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise Refused(f"host {host!r} resolves to a non-public address")
    return urllib.parse.urlunsplit(("https", host, parts.path or "/", parts.query, ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def default_opener():
    return urllib.request.build_opener(_NoRedirect)


def get(url: str, *, allowed: frozenset = ALLOWED_HOSTS, resolver: Callable = resolve, opener=None,
        sleep: Callable[[float], None] = time.sleep, timeout_s: float = 60.0) -> tuple:
    """(final URL, body bytes). Every hop is checked; a body over MAX_BYTES is refused."""
    opener = opener or default_opener()
    current = check_url(url, allowed=allowed, resolver=resolver)
    for _ in range(MAX_REDIRECTS + 1):
        last: Optional[Exception] = None
        for attempt in range(ATTEMPTS):
            req = urllib.request.Request(current, headers={"user-agent": USER_AGENT})
            try:
                with opener.open(req, timeout=timeout_s) as resp:
                    body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise Refused(f"{current}: larger than {MAX_BYTES} bytes")
                sleep(PAUSE_S)
                return current, body
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("location") or ""
                    current = check_url(urllib.parse.urljoin(current, location), allowed=allowed, resolver=resolver)
                    last = None
                    break
                if exc.code in (408, 429) or exc.code >= 500:
                    last = HttpError(exc.code, current)
                    sleep(2.0 * 2 ** attempt)
                    continue
                raise HttpError(exc.code, current) from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                last = exc
                sleep(2.0 * 2 ** attempt)
        else:
            raise last if last else RuntimeError("request failed")
        if last is not None:
            raise last
    raise Refused(f"more than {MAX_REDIRECTS} redirects")
