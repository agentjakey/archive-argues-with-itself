"""JSON Lines files: read, write whole, append one record. Every audit output is one of these, in a
format documented under docs/formats/."""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

# One lock for every append in this process: judges run in threads, and two appends to the same
# file must never interleave (a run once left half a ledger line behind). Appends also take a lock
# file beside the target, so two processes (two runs at once) cannot interleave either: on
# 2026-11-01 two runs appending to the ledger at the same moment lost the start of one line.
_APPEND_LOCK = threading.Lock()
LOCK_WAIT_S = 30.0


@contextmanager
def file_lock(path: Path):
    """An exclusive lock on <path>.lock across processes (msvcrt on Windows, fcntl elsewhere)."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"could not lock {lock_path} within {LOCK_WAIT_S:.0f} s")
                    time.sleep(0.02)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def read_jsonl(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


def iter_jsonl(path: Path) -> Iterator[dict]:
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                if not raw.endswith(chr(10)):
                    return      # the last line, still being written by another process: not yet a record
                raise ValueError(f"{path}:{line_no}: not a JSON line ({exc.msg})") from exc


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with _APPEND_LOCK, file_lock(path):
        with path.open("a", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(line)
            fh.flush()
