"""A local stand-in for the engine Worker's R2 route, for testing a container's provisioning on a
development machine. Serves HEAD and ranged GETs for the release's object keys (config/scopes.toml)
from a folder of verified files, in the same layout the boot writes (civic.db, index/dense/...,
microlog/...). Only the release's keys are served, as the Worker's R2Proxy does.

Run it in a container on a private Docker network (no port published on the host), next to the
engine container:

    docker network create r2-local
    docker run -d --name r2 --network r2-local -v <verified data>:/src:ro -v <repo>:/repo:ro
        archive-engine:local python /repo/scripts/v2/local_r2.py --root /src --host 0.0.0.0
    docker run --network r2-local -e CIVIC_PROVISION=r2-binding -e CIVIC_R2_PROXY_URL=http://r2:9311 ...
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent.parent.parent
RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")
CHUNK = 1024 * 1024


def key_layout() -> dict:
    """R2 key -> path under the root, from config/scopes.toml."""
    sys.path.insert(0, str(REPO / "src"))
    from archive_debugger import scopes
    registry = scopes.load_registry()
    layout = {}
    prefix = {"pilot": "", "microlog": "microlog/"}
    index_dir = {"pilot": "index/", "microlog": "microlog/index/"}
    for name, entry in registry["scopes"].items():
        r2, dense = entry.get("r2") or {}, entry.get("dense") or {}
        if r2:
            layout[r2["db_key"]] = prefix[name] + Path(r2["db_key"]).name
            layout[r2["index_key"]] = index_dir[name] + Path(r2["index_key"]).name
        for field in ("matrix_key", "ids_key", "manifest_key"):
            if field in dense:
                layout[dense[field]] = index_dir[name] + "dense/" + Path(dense[field]).name
    return layout


class Handler(BaseHTTPRequestHandler):
    def _file(self) -> Path | None:
        key = unquote(urlsplit(self.path).path.lstrip("/"))
        rel = self.server.layout.get(key)  # type: ignore[attr-defined]
        return None if rel is None else self.server.root / rel  # type: ignore[attr-defined]

    def do_HEAD(self) -> None:  # noqa: N802
        path = self._file()
        if path is None or not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self._file()
        if path is None or not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        size = path.stat().st_size
        match = RANGE.match(self.headers.get("Range", ""))
        start, end = (int(match.group(1)), int(match.group(2))) if match else (0, size - 1)
        end = min(end, size - 1)
        self.send_response(206 if match else 200)
        self.send_header("Content-Length", str(end - start + 1))
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                block = fh.read(min(CHUNK, left))
                if not block:
                    break
                self.wfile.write(block)
                left -= len(block)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=9311)
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to listen on; 0.0.0.0 only inside a container on a private network")
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.root = args.root  # type: ignore[attr-defined]
    server.layout = key_layout()  # type: ignore[attr-defined]
    print(f"serving {len(server.layout)} release keys from {args.root} on port {args.port}", flush=True)  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
