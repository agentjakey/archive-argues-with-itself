"""Raw-items loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.ingest import db, loader

FIXTURE = Path(__file__).parent / "fixtures" / "harvest_items_sample.jsonl"
FULL_ITEMS = Path(__file__).parent.parent / "data" / "harvest" / "items.jsonl"

# Columns that must stay NULL after a raw load (Phase-5 outputs).
NORMALIZED_COLUMNS = (
    "issuer_norm", "issuer_method", "jurisdiction_norm", "jurisdiction_method",
    "date_norm", "year", "decade", "dated", "date_method",
    "doc_type_norm", "doc_type_method",
)


@pytest.fixture
def conn():
    c = db.init_db(":memory:")
    yield c
    c.close()


def test_loads_fixture_rows(conn):
    n = loader.load_raw_items(conn, FIXTURE)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_raw_columns_populated(conn):
    loader.load_raw_items(conn, FIXTURE)
    row = conn.execute("SELECT * FROM items WHERE item_id='04assessmentofstat00onta'").fetchone()
    assert row is not None
    assert row["mediatype"] == "texts"
    assert row["publisher_raw"] == "Ontario Ministry of the Environment"
    assert row["date_raw"] == "1986-01-01T00:00:00Z"
    assert row["ocr_format"] == "hOCR"
    assert row["has_word_coords"] == 1
    assert row["ocr_file_ref"] and row["ocr_file_ref"].startswith("ocr/")
    assert row["details_url"] == "https://archive.org/details/04assessmentofstat00onta"
    assert row["ingest_ts"]  # stamped
    # collection_raw preserved as JSON (a list was stored)
    assert "governmentpublications" in row["collection_raw"]


def test_normalized_columns_are_null(conn):
    loader.load_raw_items(conn, FIXTURE)
    cols = ", ".join(NORMALIZED_COLUMNS)
    for row in conn.execute(f"SELECT {cols} FROM items").fetchall():
        for col in NORMALIZED_COLUMNS:
            assert row[col] is None, f"{col} should be NULL after a raw load"


def test_preliminary_year_is_ignored(conn):
    # The fixture record carries a preliminary year (1986); the loader must NOT
    # write it to the normalized year column.
    loader.load_raw_items(conn, FIXTURE)
    year = conn.execute("SELECT year FROM items WHERE item_id='04assessmentofstat00onta'").fetchone()[0]
    assert year is None


def test_reload_is_idempotent(conn):
    loader.load_raw_items(conn, FIXTURE)
    loader.load_raw_items(conn, FIXTURE)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2  # no duplicates


@pytest.mark.skipif(not FULL_ITEMS.exists(), reason="harvested data/harvest/items.jsonl not present")
def test_full_corpus_loads(conn):
    n = loader.load_raw_items(conn, FULL_ITEMS)
    assert n == 3477
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 3477
    # PK uniqueness: distinct item_ids equal row count.
    assert conn.execute("SELECT COUNT(DISTINCT item_id) FROM items").fetchone()[0] == 3477
    # Raw columns populated on essentially all rows.
    assert conn.execute("SELECT COUNT(*) FROM items WHERE mediatype IS NOT NULL").fetchone()[0] == 3477
    assert conn.execute("SELECT COUNT(*) FROM items WHERE ocr_file_ref IS NOT NULL").fetchone()[0] == 3477
    # All normalized columns NULL across the whole corpus.
    for col in NORMALIZED_COLUMNS:
        assert conn.execute(f"SELECT COUNT(*) FROM items WHERE {col} IS NOT NULL").fetchone()[0] == 0
