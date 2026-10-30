"""The Railway redirect: every request to the old *.up.railway.app address gets a 301 to the same
path and query on the new domain. Railway cannot redirect its own domain, so a running service
has to answer (docs/v2/HOSTING.md, "Railway redirect").

Standard library only, no volume, a few MB of memory. A path that moved is mapped first
(PATH_MAP: old API permalinks open the reading room), everything else keeps its path. Nothing
about a request is logged except its method, the status and the target path's first segment.

    REDIRECT_TARGET=https://archiveargues.org PORT=8080 python redirect_app.py
"""
from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit

DEFAULT_TARGET = "https://archiveargues.org"
HEALTH_PATH = "/__redirect_health"     # Railway's health check expects a 200; nothing else gets one
# Paths that changed in the move. /ask?q=... was the API permalink; the same query opens the
# question in the reading room at /. /health now lives on the engine Worker.
PATH_MAP = {
    "/ask": ("", "/"),
    "/health": ("https://api.archiveargues.org", "/health"),
}


def target_for(raw_path: str, target: str) -> str:
    """The redirect location for a request path (with its query), on the target origin."""
    parts = urlsplit(raw_path)
    path = parts.path or "/"
    origin = urlsplit(target)
    scheme, netloc = origin.scheme, origin.netloc
    mapped = PATH_MAP.get(path.rstrip("/") or "/")
    if mapped:
        other_origin, path = mapped
        if other_origin:
            moved = urlsplit(other_origin)
            scheme, netloc = moved.scheme, moved.netloc
    return urlunsplit((scheme, netloc, path, parts.query, ""))


class Redirect(BaseHTTPRequestHandler):
    server_version = "archive-redirect"
    sys_version = ""

    def _redirect(self, body: bool) -> None:
        location = target_for(self.path, self.server.target)  # type: ignore[attr-defined]
        message = f"Moved to {location}\n".encode("utf-8")
        self.send_response(301)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        if body:
            self.wfile.write(message)

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        if urlsplit(self.path).path == HEALTH_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        self._redirect(body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._redirect(body=False)

    def do_POST(self) -> None:  # noqa: N802
        self._redirect(body=True)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server's signature
        first = urlsplit(self.path).path.split("/")[1:2]
        sys.stderr.write(f"{self.command} 301 /{first[0] if first else ''}\n")


def make_server(port: int, target: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), Redirect)
    server.target = target.rstrip("/")  # type: ignore[attr-defined]
    return server


def main() -> int:
    target = os.environ.get("REDIRECT_TARGET", DEFAULT_TARGET)
    if not target.startswith("https://"):
        print("REDIRECT_TARGET must be an https origin", file=sys.stderr)
        return 2
    server = make_server(int(os.environ.get("PORT", "8080")), target)
    print(f"redirecting every request to {target}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
