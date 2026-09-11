"""Data release: checksums for the two data files, and the boot-time fetch that a
container runs before serving.

Publishing (laptop, once): scripts/make_data_release.py writes data-release.sha256
(sha256sum format, one line per asset) and prints the `gh release create` command.

Booting (container): `python -m archive_debugger.data_release` reads CIVIC_DB_PATH,
CIVIC_INDEX_PATH and DATA_RELEASE_URL (the base URL of the release assets). For
each file: present and matching the published checksum -> keep; absent or
mismatching -> download with HTTP Range resume into `<name>.part`, verify, rename.
Progress is logged every 100 MB. Standard library only; the only network calls are
to DATA_RELEASE_URL (N1: nothing here touches the Internet Archive)."""
from __future__ import annotations

import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

CHECKSUM_FILE = "data-release.sha256"
CHUNK = 8 * 1024 * 1024
LOG_EVERY = 100 * 1024 * 1024
ASSETS = {"civic.db": "CIVIC_DB_PATH", "vectors.db": "CIVIC_INDEX_PATH"}
DEFAULTS = {"CIVIC_DB_PATH": "/data/civic.db", "CIVIC_INDEX_PATH": "/data/index/vectors.db"}
ATTEMPTS = 8
TIMEOUT = 120


class ChecksumMismatch(RuntimeError):
    pass


def _mb(n: int) -> str:
    return f"{n / 1_000_000:,.0f} MB"


def sha256_file(path: Path, log: Optional[Callable[[str], None]] = None) -> str:
    h = hashlib.sha256()
    done = 0
    next_log = LOG_EVERY
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
            done += len(block)
            if log and done >= next_log:
                log(f"  verifying {Path(path).name}: {_mb(done)}")
                next_log += LOG_EVERY
    return h.hexdigest()


def write_checksums(files: dict, out: Path, log: Callable[[str], None] = print) -> str:
    """files: {asset_name: local_path}. Writes sha256sum-compatible lines and returns the text."""
    lines = []
    for name, path in files.items():
        log(f"hashing {path} ({_mb(Path(path).stat().st_size)})")
        lines.append(f"{sha256_file(Path(path), log)}  {name}")
    text = "\n".join(lines) + "\n"
    Path(out).write_text(text, encoding="utf-8")
    return text


def parse_checksums(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        name = name.strip().lstrip("*")
        if len(digest) != 64 or not name:
            raise ValueError(f"bad checksum line: {line!r}")
        out[name] = digest.lower()
    return out


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def download(url: str, dest: Path, log: Callable[[str], None] = print) -> None:
    """Resumable download to dest via dest.part. A 206 appends to the partial file; a 200
    (server ignored Range, or nothing partial) restarts; 416 with a partial file means
    the partial file is already complete."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:
            log(f"  {dest.name}: partial file already complete ({_mb(have)})")
            part.replace(dest)
            return
        raise
    status = getattr(resp, "status", None) or 200
    if status == 206 and have:
        mode, done = "ab", have
        log(f"  {dest.name}: resuming at {_mb(have)}")
    else:
        mode, done = "wb", 0
        if have:
            log(f"  {dest.name}: server does not resume; starting over")
    total = None
    length = resp.headers.get("Content-Length")
    if length:
        total = done + int(length)
    next_log = (done // LOG_EVERY + 1) * LOG_EVERY
    t0 = time.perf_counter()
    with resp, part.open(mode) as fh:
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            fh.write(block)
            done += len(block)
            if done >= next_log:
                rate = (done - have) / max(time.perf_counter() - t0, 1e-6) / 1_000_000
                of = f" of {_mb(total)}" if total else ""
                log(f"  {dest.name}: {_mb(done)}{of}  {rate:,.0f} MB/s")
                next_log += LOG_EVERY
    part.replace(dest)
    log(f"  {dest.name}: downloaded {_mb(done)} in {time.perf_counter() - t0:,.0f} s")


def ensure_data(targets: dict, base_url: Optional[str], log: Callable[[str], None] = print) -> dict:
    """targets: {asset_name: Path}. Returns {asset_name: 'verified' | 'downloaded' | 'present-unverified'}.
    Raises ChecksumMismatch when a fresh download does not match the published checksum."""
    result = {}
    if not base_url:
        missing = [n for n, p in targets.items() if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"missing {missing} and DATA_RELEASE_URL is not set")
        for n in targets:
            result[n] = "present-unverified"
        log("DATA_RELEASE_URL not set; data files present, checksums not verified")
        return result
    base = base_url.rstrip("/")
    checksums = parse_checksums(fetch_text(f"{base}/{CHECKSUM_FILE}"))
    for name, path in targets.items():
        path = Path(path)
        if name not in checksums:
            raise KeyError(f"{CHECKSUM_FILE} at {base} has no entry for {name}")
        if path.exists():
            log(f"{name}: present ({_mb(path.stat().st_size)}), verifying")
            if sha256_file(path, log) == checksums[name]:
                log(f"{name}: checksum ok")
                result[name] = "verified"
                continue
            log(f"{name}: checksum MISMATCH, re-downloading")
            path.unlink()
        log(f"{name}: downloading from {base}/{name}")
        download(f"{base}/{name}", path, log)
        if sha256_file(path, log) != checksums[name]:
            path.unlink(missing_ok=True)
            raise ChecksumMismatch(f"{name}: downloaded file does not match {CHECKSUM_FILE}; removed")
        log(f"{name}: checksum ok")
        result[name] = "downloaded"
    return result


def main(argv=None) -> int:
    log = lambda m: print(m, flush=True)  # noqa: E731
    targets = {name: Path(os.environ.get(var) or DEFAULTS[var]) for name, var in ASSETS.items()}
    base_url = os.environ.get("DATA_RELEASE_URL")
    for attempt in range(1, ATTEMPTS + 1):
        try:
            result = ensure_data(targets, base_url, log)
            log(f"data ready: {result}")
            return 0
        except FileNotFoundError as exc:
            log(f"{exc}; set DATA_RELEASE_URL or place the files; retrying in 30 s")
            time.sleep(30)
        except ChecksumMismatch as exc:
            log(f"{exc}; attempt {attempt}/{ATTEMPTS}")
            time.sleep(min(60, 5 * attempt))
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log(f"download error: {type(exc).__name__}: {exc}; attempt {attempt}/{ATTEMPTS}, partial file kept for resume")
            time.sleep(min(120, 10 * attempt))
    log("giving up after repeated failures")
    return 1


if __name__ == "__main__":
    sys.exit(main())
