"""The kiosk's local server: the exhibit with no network, on the kiosk machine itself.

It serves one assembled site release (scripts/v2/build_release.py) from the kiosk's releases folder,
on 127.0.0.1 only, with the release's own _headers (the same CSP and caching as the website). The
current release is named in one pointer file, so installing a release is copying a folder and moving
the pointer, and rolling back is moving it back. Standard library only.

It adds two things the website does not have:
  GET  /exhibit/kiosk.json   tells the app it is on a kiosk (idle reset, printer present)
  POST /exhibit/count        one event word (for example "same_or_not:start"); the server adds it to
                             that day's totals. Daily totals only: no time of day, no visitor, no
                             session, no answer text, nothing per visit. Written to
                             <counts>/<YYYY-MM-DD>.json every minute and on exit.

    python exhibit/kiosk/serve.py --root C:\\Exhibit                      serve the current release
    python exhibit/kiosk/serve.py --root C:\\Exhibit install build\\release   copy a release in and point to it
    python exhibit/kiosk/serve.py --root C:\\Exhibit rollback                  point back to the previous release
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

POINTER = "current.txt"
HISTORY = "history.txt"
EVENT = re.compile(r"^[a-z_]{1,32}(:[a-z_]{1,32})?$")
MAX_EVENTS_PER_DAY = 200_000     # a stuck input cannot fill the disk
FLUSH_S = 60


def parse_headers(text: str) -> list:
    """[(pattern, [(name, value)])] from a Cloudflare _headers file."""
    rules, current = [], None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            current = (raw.strip(), [])
            rules.append(current)
        elif current is not None and ":" in raw:
            name, value = raw.strip().split(":", 1)
            current[1].append((name.strip(), value.strip()))
    return rules


def headers_for(rules: list, path: str) -> list:
    out = []
    for pattern, headers in rules:
        if pattern == path or (pattern.endswith("*") and fnmatch.fnmatchcase(path, pattern)):
            out.extend(headers)
    return out


class DailyCounts:
    def __init__(self, folder: Path):
        self.folder = folder
        self.lock = threading.Lock()
        self.day = date.today().isoformat()
        self.counts = self._load(self.day)

    def _path(self, day: str) -> Path:
        return self.folder / f"{day}.json"

    def _load(self, day: str) -> dict:
        path = self._path(day)
        if path.exists():
            try:
                return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
            except (ValueError, AttributeError):
                return {}
        return {}

    def add(self, event: str) -> bool:
        if not EVENT.match(event):
            return False
        with self.lock:
            today = date.today().isoformat()
            if today != self.day:
                self._flush_locked()
                self.day, self.counts = today, self._load(today)
            if sum(self.counts.values()) >= MAX_EVENTS_PER_DAY:
                return False
            self.counts[event] = self.counts.get(event, 0) + 1
        return True

    def _flush_locked(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self._path(self.day).with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(sorted(self.counts.items())), indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self._path(self.day))

    def flush(self) -> None:
        with self.lock:
            self._flush_locked()


def make_handler(release: Path, rules: list, counts: DailyCounts, kiosk_config: dict):
    class Handler(SimpleHTTPRequestHandler):
        server_version = "exhibit-kiosk"
        sys_version = ""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(release), **kwargs)

        def log_message(self, fmt, *args):   # no access log: nothing about visits is kept
            return

        def end_headers(self):
            for name, value in headers_for(rules, self.path.split("?", 1)[0]):
                self.send_header(name, value)
            super().end_headers()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/exhibit/kiosk.json":
                body = json.dumps(kiosk_config).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("content-type", "application/json")
                self.send_header("cache-control", "no-store")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path in ("/", "/exhibit"):
                self.send_response(HTTPStatus.FOUND)
                self.send_header("location", "/exhibit/")
                self.end_headers()
                return
            super().do_GET()

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/exhibit/count":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            length = min(int(self.headers.get("content-length") or 0), 80)
            event = self.rfile.read(length).decode("ascii", errors="replace").strip()
            ok = counts.add(event)
            self.send_response(HTTPStatus.NO_CONTENT if ok else HTTPStatus.BAD_REQUEST)
            self.end_headers()

    return Handler


def current_release(root: Path) -> Path:
    pointer = root / POINTER
    if not pointer.exists():
        raise SystemExit(f"{pointer} is missing: install a release first")
    release = root / "releases" / pointer.read_text(encoding="utf-8").strip()
    if not (release / "exhibit" / "index.html").exists():
        raise SystemExit(f"{release} has no exhibit/index.html")
    return release


def install(root: Path, release: Path) -> str:
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", manifest["release_id"])
    target = root / "releases" / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(release, target)
    previous = (root / POINTER).read_text(encoding="utf-8").strip() if (root / POINTER).exists() else ""
    if previous:
        with (root / HISTORY).open("a", encoding="utf-8") as fh:
            fh.write(previous + "\n")
    (root / POINTER).write_text(name + "\n", encoding="utf-8")
    return name


def rollback(root: Path) -> str:
    history = [h for h in (root / HISTORY).read_text(encoding="utf-8").splitlines() if h.strip()] \
        if (root / HISTORY).exists() else []
    if not history:
        raise SystemExit("no earlier release to roll back to")
    previous = history.pop()
    (root / HISTORY).write_text("".join(h + "\n" for h in history), encoding="utf-8")
    (root / POINTER).write_text(previous + "\n", encoding="utf-8")
    return previous


def serve(root: Path, port: int, idle_reset: int, printer: bool) -> None:
    release = current_release(root)
    rules = parse_headers((release / "_headers").read_text(encoding="utf-8")) if (release / "_headers").exists() else []
    counts = DailyCounts(root / "counts")
    config = {"kiosk": True, "idle_reset_seconds": idle_reset, "printer": printer}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(release, rules, counts, config))
    stop = threading.Event()

    def flusher():
        while not stop.wait(FLUSH_S):
            counts.flush()
    threading.Thread(target=flusher, daemon=True).start()
    print(f"serving {release.name} on http://127.0.0.1:{port}/exhibit/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        counts.flush()
        httpd.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True, help="the kiosk folder: releases/, counts/, current.txt")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--idle-reset", type=int, default=60)
    ap.add_argument("--printer", action="store_true", help="a receipt printer is attached")
    sub = ap.add_subparsers(dest="cmd")
    i = sub.add_parser("install")
    i.add_argument("release", type=Path)
    sub.add_parser("rollback")
    args = ap.parse_args(argv)
    if args.cmd == "install":
        print(f"installed {install(args.root, args.release)}")
        return 0
    if args.cmd == "rollback":
        print(f"now serving {rollback(args.root)}")
        return 0
    serve(args.root, args.port, args.idle_reset, args.printer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
