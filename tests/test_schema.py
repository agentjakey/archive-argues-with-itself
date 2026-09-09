"""Schema migration and round-trip tests."""

from __future__ import annotations

import pytest

from archive_debugger.ingest import db, schema


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


def test_migrate_creates_expected_tables(conn):
    tables = db.table_names(conn)
    for name in schema.EXPECTED_TABLES:
        assert name in tables, f"missing table {name}"


def test_no_bbox_or_coordinate_columns_anywhere(conn):
    # N3: no coordinate storage anywhere in the schema.
    banned = ("bbox", "coord", "x0", "y0", "x1", "y1", "_x", "_y", "pixel", "polygon")
    allowed = {"has_word_coords"}  # the sanctioned boolean capability flag (N3)
    for table in schema.EXPECTED_TABLES:
        if table == "passages_fts":
            continue
        for col in db.column_names(conn, table):
            if col in allowed:
                continue
            low = col.lower()
            assert not any(b in low for b in banned), f"coordinate-like column {table}.{col}"


def test_has_word_coords_is_the_only_word_coord_artifact(conn):
    cols = db.column_names(conn, "items")
    assert "has_word_coords" in cols
    # It is a flag; there must be no column storing the actual coordinates.
    assert not any(c.lower().endswith("_coords") and c != "has_word_coords" for c in cols)


def test_round_trip_one_row_per_table(conn):
    conn.execute(
        "INSERT INTO items (item_id, title, mediatype, has_word_coords) VALUES (?,?,?,?)",
        ("itemA", "Title A", "texts", 1),
    )
    conn.execute(
        "INSERT INTO pages (page_id, item_id, leaf_index, char_count, has_text) VALUES (?,?,?,?,?)",
        ("itemA:0", "itemA", 0, 100, 1),
    )
    conn.execute(
        "INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        ("itemA:0:0", "itemA", "itemA:0", 0, 0, 20, "housing policy text", 3, "ok"),
    )
    conn.execute(
        "INSERT INTO coverage_cells (period, jurisdiction, issuer, doc_type, item_count) VALUES (?,?,?,?,?)",
        ("1980s", "Ontario", "Ministry", "Report", 5),
    )
    conn.execute(
        "INSERT INTO eval_questions (qid, text, topic) VALUES (?,?,?)",
        ("q1", "What did governments say?", "public_health"),
    )
    conn.execute(
        "INSERT INTO eval_labels (qid, passage_id, relevance) VALUES (?,?,?)",
        ("q1", "itemA:0:0", 1),
    )
    conn.execute(
        "INSERT INTO eval_runs (run_id, git_sha, config_json, ts) VALUES (?,?,?,?)",
        ("run1", "abc123", "{}", "2026-09-08T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO eval_results (run_id, qid, metric, value) VALUES (?,?,?,?)",
        ("run1", "q1", "recall@10", 0.5),
    )
    conn.execute(
        "INSERT INTO gaps (gap_id, gap_type, scope, metric, value, examples_json) VALUES (?,?,?,?,?,?)",
        ("g1", "undated", "corpus", "fraction", 0.285, "[]"),
    )
    conn.commit()

    assert conn.execute("SELECT title FROM items WHERE item_id='itemA'").fetchone()[0] == "Title A"
    assert conn.execute("SELECT char_count FROM pages WHERE page_id='itemA:0'").fetchone()[0] == 100
    assert conn.execute("SELECT text FROM passages WHERE passage_id='itemA:0:0'").fetchone()[0] == "housing policy text"
    assert conn.execute("SELECT item_count FROM coverage_cells").fetchone()[0] == 5
    assert conn.execute("SELECT topic FROM eval_questions WHERE qid='q1'").fetchone()[0] == "public_health"
    assert conn.execute("SELECT relevance FROM eval_labels WHERE qid='q1'").fetchone()[0] == 1
    assert conn.execute("SELECT git_sha FROM eval_runs WHERE run_id='run1'").fetchone()[0] == "abc123"
    assert conn.execute("SELECT value FROM eval_results WHERE run_id='run1'").fetchone()[0] == 0.5
    assert conn.execute("SELECT gap_type FROM gaps WHERE gap_id='g1'").fetchone()[0] == "undated"


def test_fts_is_populated_by_trigger(conn):
    conn.execute("INSERT INTO items (item_id) VALUES ('i')")
    conn.execute("INSERT INTO pages (page_id, item_id) VALUES ('i:0','i')")
    conn.execute(
        "INSERT INTO passages (passage_id, item_id, page_id, text) VALUES (?,?,?,?)",
        ("i:0:0", "i", "i:0", "communicable disease sanitation report"),
    )
    conn.commit()
    hit = conn.execute("SELECT passage_id FROM passages p JOIN passages_fts f ON p.rowid=f.rowid WHERE passages_fts MATCH 'sanitation'").fetchone()
    assert hit is not None and hit[0] == "i:0:0"


def test_foreign_key_enforced(conn):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO pages (page_id, item_id) VALUES ('p','no_such_item')")
        conn.commit()
