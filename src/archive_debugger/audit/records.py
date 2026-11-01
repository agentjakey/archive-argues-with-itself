"""JSON Lines files: read, write whole, append one record. Every audit output is one of these, in a
format documented under docs/formats/."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterable, Iterator

# One lock for every append in this process: judges run in threads, and two appends to the same
# file must never interleave (a run once left half a ledger line behind).
_APPEND_LOCK = threading.Lock()


def read_jsonl(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


def iter_jsonl(path: Path) -> Iterator[dict]:
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
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
    with _APPEND_LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
