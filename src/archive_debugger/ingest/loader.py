"""Raw-items loader (Phase 3).

Loads harvested items from items.jsonl into the items table, filling ONLY the
raw/harvest columns. Every normalized column is left NULL: those are Phase-5
outputs and Phase 5 is the single source of truth for normalization.

Deliberately ignores any preliminary dated/year carried in items.jsonl, so no
normalized value ever originates from the harvest layer.

No OCR parsing, no normalization, no network.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from archive_debugger.ingest import db

# The raw/harvest columns this loader is allowed to populate. Everything else on
# the items table (the normalized *_norm / *_method columns, plus year, decade,
# dated) stays NULL for Phase 5.
RAW_COLUMNS = (
    "item_id",
    "title",
    "creator_raw",
    "publisher_raw",
    "date_raw",
    "collection_raw",
    "language",
    "mediatype",
    "ocr_format",
    "ocr_engine",
    "has_word_coords",
    "has_printed_page_map",
    "page_count",
    "ocr_file_ref",
    "details_url",
    "license",
    "ingest_ts",
)


def _raw_text(value) -> Optional[str]:
    """Preserve a raw metadata value as text. Lists (creator, publisher,
    collection) are JSON-encoded so nothing is collapsed or lost; strings pass
    through; None stays NULL."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _as_bool_int(value) -> Optional[int]:
    if value is None:
        return None
    return 1 if value else 0


def record_to_raw_row(record: dict, ingest_ts: str) -> dict:
    """Map an items.jsonl record to the raw items columns. year/dated are NOT
    read; those columns are Phase-5 outputs."""
    return {
        "item_id": record.get("identifier"),
        "title": record.get("title"),
        "creator_raw": _raw_text(record.get("creator_raw")),
        "publisher_raw": _raw_text(record.get("publisher_raw")),
        "date_raw": record.get("date_raw"),
        "collection_raw": _raw_text(record.get("collection_raw")),
        "language": _raw_text(record.get("language")),
        "mediatype": record.get("mediatype"),
        "ocr_format": record.get("ocr_format"),
        "ocr_engine": record.get("ocr_engine"),
        "has_word_coords": _as_bool_int(record.get("has_word_coords")),
        "has_printed_page_map": _as_bool_int(record.get("has_printed_page_map")),
        "page_count": record.get("page_count"),
        "ocr_file_ref": record.get("ocr_file_ref"),
        "details_url": record.get("details_url"),
        "license": record.get("license"),
        "ingest_ts": ingest_ts,
    }


def load_raw_items(conn: sqlite3.Connection, items_path: Path) -> int:
    """Load items.jsonl into items, raw columns only. Returns the row count.
    Uses INSERT OR REPLACE so a reload is idempotent on item_id."""
    ingest_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    placeholders = ", ".join(["?"] * len(RAW_COLUMNS))
    columns = ", ".join(RAW_COLUMNS)
    sql = f"INSERT OR REPLACE INTO items ({columns}) VALUES ({placeholders})"

    count = 0
    with items_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            row = record_to_raw_row(record, ingest_ts)
            conn.execute(sql, [row[c] for c in RAW_COLUMNS])
            count += 1
    conn.commit()
    return count


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Load harvested items into civic.db (raw columns only).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--items", default="data/harvest/items.jsonl", type=Path)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    db_path = db.resolve_db_path(args.config)
    conn = db.init_db(db_path)
    try:
        count = load_raw_items(conn, args.items)
    finally:
        conn.close()
    print(f"Loaded {count} items into {db_path} (raw columns only; normalized columns NULL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
