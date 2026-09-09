"""Corpus parse driver (Phase 4, steps 4-5).

Local only: reads each item's assigned segmentation source from raw/ and writes
pages + passages (and citation-alignment gaps) into civic.db. No network.

For every item it extracts BOTH text and page boundaries from the SAME chosen
file (never aligns flat-text offsets to external boundaries):
  DjVuTXT -> form-feed split;  DjVuXML -> OBJECT-per-page (streamed).
hOCR is never used here (the corpus assigned none). Page count is validated
against page_numbers.json; a mismatch is flagged, never silently accepted.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional

from archive_debugger.ingest import db, ocr


def content_path(cache_dir: Path, md5: str, name: str) -> Path:
    return cache_dir / "ocr" / md5[:2] / f"{md5}__{os.path.basename(name)}"


def _cached_source(record: dict, cache_dir: Path) -> Optional[Path]:
    entry = record.get("ocr_file")
    if not entry or not entry.get("md5") or not entry.get("name"):
        return None
    path = content_path(cache_dir, entry["md5"], entry["name"])
    return path if path.exists() else None


def _printed_pages(record: dict, cache_dir: Path) -> Optional[list]:
    if not record.get("has_printed_page_map"):
        return None
    pn = record.get("page_numbers_file")
    if not pn or not pn.get("md5") or not pn.get("name"):
        return None
    path = content_path(cache_dir, pn["md5"], pn["name"])
    if not path.exists():
        return None
    try:
        return ocr.load_printed_pages(path)
    except (json.JSONDecodeError, OSError):
        return None


def _parse_pages(record: dict, source_path: Path) -> list[str]:
    fmt = record["ocr_format"]
    if fmt == "DjVuXML":
        return ocr.parse_djvu_xml_file(source_path)
    if fmt == "DjVuTXT":
        return ocr.parse_djvutxt(source_path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"ocr_format not usable in corpus parse: {fmt}")


def _write_item(conn: sqlite3.Connection, item_id: str, pages: list[dict], passages: list[dict]) -> None:
    # Idempotent: clear any prior parse for this item first (passages before pages
    # for the FK), then insert fresh.
    conn.execute("DELETE FROM passages WHERE item_id=?", (item_id,))
    conn.execute("DELETE FROM pages WHERE item_id=?", (item_id,))
    conn.executemany(
        "INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, ocr_conf_mean, has_text)"
        " VALUES (?,?,?,?,?,?,?)",
        [(p["page_id"], p["item_id"], p["leaf_index"], p["printed_page"], p["char_count"], p["ocr_conf_mean"], p["has_text"]) for p in pages],
    )
    conn.executemany(
        "INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_conf_mean, ocr_quality, embedding_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(p["passage_id"], p["item_id"], p["page_id"], p["leaf_index"], p["char_start"], p["char_end"], p["text"], p["token_count"], p["ocr_conf_mean"], p["ocr_quality"], p["embedding_id"]) for p in passages],
    )


def _flag_alignment(conn: sqlite3.Connection, item_id: str, parsed: int, expected: Optional[int]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO gaps (gap_id, gap_type, scope, metric, value, examples_json) VALUES (?,?,?,?,?,?)",
        (f"align:{item_id}", "citation-alignment-risk", item_id, "parsed_vs_leaves",
         float(parsed), json.dumps({"parsed_pages": parsed, "page_map_leaves": expected})),
    )


def build_corpus(conn: sqlite3.Connection, records: list[dict], cache_dir: Path, *, limit: Optional[int] = None) -> dict:
    stats = {
        "items_parsed": 0,
        "items_pending_download": 0,
        "total_pages": 0,
        "total_passages": 0,
        "by_source": Counter(),
        "quality_buckets": Counter(),
        "alignment_risk": 0,
        "zero_usable_text_items": 0,
    }
    n = 0
    for record in records:
        if limit is not None and n >= limit:
            break
        source_path = _cached_source(record, cache_dir)
        if source_path is None:
            stats["items_pending_download"] += 1
            continue
        item_id = record["identifier"]
        printed = _printed_pages(record, cache_dir)
        expected = len(printed) if printed is not None else None

        page_texts = _parse_pages(record, source_path)
        parsed_count = len(page_texts)
        pages = ocr.build_pages(item_id, page_texts, printed)
        passages: list[dict] = []
        for page in pages:
            passages.extend(ocr.build_passages(item_id, page))

        _write_item(conn, item_id, pages, passages)
        if expected is not None and parsed_count != expected:
            _flag_alignment(conn, item_id, parsed_count, expected)
            stats["alignment_risk"] += 1

        stats["items_parsed"] += 1
        stats["by_source"][record.get("segmentation_source") or record["ocr_format"]] += 1
        stats["total_pages"] += len(pages)
        stats["total_passages"] += len(passages)
        for p in passages:
            stats["quality_buckets"][ocr.quality_bucket(p["ocr_quality"])] += 1
        if not any(p["has_text"] for p in pages):
            stats["zero_usable_text_items"] += 1
        n += 1
    conn.commit()
    stats["by_source"] = dict(stats["by_source"])
    stats["quality_buckets"] = dict(stats["quality_buckets"])
    return stats


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parse cached OCR into pages/passages in civic.db.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--items", default="data/harvest/items.jsonl", type=Path)
    p.add_argument("--cache-dir", default="raw", type=Path)
    p.add_argument("--limit", type=int, default=None)
    return p


def _read_records(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    conn = db.init_db(db.resolve_db_path(args.config))
    try:
        records = _read_records(args.items)
        stats = build_corpus(conn, records, args.cache_dir, limit=args.limit)
    finally:
        conn.close()
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
