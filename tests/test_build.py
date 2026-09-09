"""Corpus parse-driver tests (pages/passages into civic.db)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archive_debugger.ingest import build, db

FX = Path(__file__).parent / "fixtures" / "ocr"


@pytest.fixture
def conn():
    c = db.init_db(":memory:")
    yield c
    c.close()


def _place(cache_dir: Path, md5: str, name: str, src: Path) -> None:
    dest = build.content_path(cache_dir, md5, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def _seed_item(conn, item_id: str) -> None:
    # pages/passages FK to items; the real pipeline loads items before parsing.
    conn.execute("INSERT OR IGNORE INTO items (item_id) VALUES (?)", (item_id,))
    conn.commit()


def test_build_from_djvuxml_writes_pages_and_passages(conn, tmp_path):
    cache = tmp_path / "raw"
    _place(cache, "md5xml", "itemA_djvu.xml", FX / "sample_djvu.xml")
    _seed_item(conn, "itemA")
    record = {
        "identifier": "itemA",
        "ocr_format": "DjVuXML",
        "segmentation_source": "djvuxml",
        "ocr_file": {"md5": "md5xml", "name": "itemA_djvu.xml"},
        "has_printed_page_map": False,
    }
    stats = build.build_corpus(conn, [record], cache)
    assert stats["items_parsed"] == 1
    assert stats["total_pages"] == 2          # two OBJECTs in the fixture
    assert stats["total_passages"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM pages WHERE item_id='itemA'").fetchone()[0] == 2
    # every passage carries exactly one leaf and no coordinates
    for row in conn.execute("SELECT leaf_index, ocr_conf_mean, embedding_id FROM passages"):
        assert isinstance(row[0], int)
        assert row[1] is None and row[2] is None
    # FTS is populated via trigger
    assert conn.execute("SELECT COUNT(*) FROM passages_fts WHERE passages_fts MATCH 'Ontario'").fetchone()[0] >= 1


def test_build_skips_items_without_cached_source(conn, tmp_path):
    record = {"identifier": "gone", "ocr_format": "DjVuXML",
              "ocr_file": {"md5": "x", "name": "gone_djvu.xml"}, "has_printed_page_map": False}
    stats = build.build_corpus(conn, [record], tmp_path / "raw")
    assert stats["items_parsed"] == 0
    assert stats["items_pending_download"] == 1


def test_build_is_idempotent(conn, tmp_path):
    cache = tmp_path / "raw"
    _place(cache, "md5xml", "itemA_djvu.xml", FX / "sample_djvu.xml")
    _seed_item(conn, "itemA")
    record = {"identifier": "itemA", "ocr_format": "DjVuXML",
              "ocr_file": {"md5": "md5xml", "name": "itemA_djvu.xml"}, "has_printed_page_map": False}
    build.build_corpus(conn, [record], cache)
    build.build_corpus(conn, [record], cache)  # re-run must not duplicate
    assert conn.execute("SELECT COUNT(*) FROM pages WHERE item_id='itemA'").fetchone()[0] == 2


def test_build_flags_page_count_mismatch(conn, tmp_path):
    cache = tmp_path / "raw"
    _place(cache, "md5xml", "itemA_djvu.xml", FX / "sample_djvu.xml")   # 2 pages
    _seed_item(conn, "itemA")
    # page map claims 5 leaves -> mismatch must be flagged in gaps, not hidden.
    import json
    pn = build.content_path(cache, "md5pn", "itemA_page_numbers.json")
    pn.parent.mkdir(parents=True, exist_ok=True)
    pn.write_text(json.dumps({"pages": [{"pageNumber": str(i)} for i in range(5)]}), encoding="utf-8")
    record = {"identifier": "itemA", "ocr_format": "DjVuXML",
              "ocr_file": {"md5": "md5xml", "name": "itemA_djvu.xml"},
              "page_numbers_file": {"md5": "md5pn", "name": "itemA_page_numbers.json"},
              "has_printed_page_map": True}
    stats = build.build_corpus(conn, [record], cache)
    assert stats["alignment_risk"] == 1
    row = conn.execute("SELECT gap_type FROM gaps WHERE scope='itemA'").fetchone()
    assert row[0] == "citation-alignment-risk"
