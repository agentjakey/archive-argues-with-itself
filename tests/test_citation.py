"""Phase 8 page-level citation + N2 verifier tests. Hermetic."""
from __future__ import annotations

import sqlite3

from archive_debugger.ingest import db, schema
from archive_debugger.retrieve import citation


def _seed(conn, *, item="itemA", leaf=0, printed=None, pid="itemA#0:0"):
    conn.execute("INSERT OR IGNORE INTO items (item_id) VALUES (?)", (item,))
    page_id = f"{item}#{leaf}"
    conn.execute("INSERT OR IGNORE INTO pages (page_id, item_id, leaf_index, printed_page) VALUES (?,?,?,?)",
                 (page_id, item, leaf, printed))
    conn.execute("INSERT OR IGNORE INTO passages (passage_id, item_id, page_id, leaf_index, text) VALUES (?,?,?,?,?)",
                 (pid, item, page_id, leaf, "x"))
    conn.commit()


def test_deep_link_wellformed():
    assert citation.deep_link("abc123", 0) == "https://archive.org/details/abc123/page/n0"
    assert citation.deep_link("x", 131) == "https://archive.org/details/x/page/n131"


def test_page_url_builders():
    assert citation.page_thumb("abc", 7) == "https://archive.org/download/abc/page/n7_thumb.jpg"
    assert citation.page_image("abc", 7) == "https://archive.org/download/abc/page/n7_medium.jpg"
    assert citation.embed_url("abc", 7) == "https://archive.org/embed/abc#page/n7"


def test_citation_printed_page_null_safe():
    conn = db.init_db(":memory:")
    _seed(conn, printed=None)
    c = citation.citation_for(conn, "itemA#0:0")
    assert c.printed_page is None
    assert c.deep_link == "https://archive.org/details/itemA/page/n0"
    assert set(c.to_dict()) == {"passage_id", "item_id", "leaf_index", "printed_page", "deep_link"}
    conn.close()


def test_citation_printed_page_present():
    conn = db.init_db(":memory:")
    _seed(conn, printed="12")
    assert citation.citation_for(conn, "itemA#0:0").printed_page == "12"
    conn.close()


def test_alignment_risk_item_resolves_page_level():
    # Mirrors healthsafetyonjo00albe_3: map dropped (printed_page NULL), leaf present.
    conn = db.init_db(":memory:")
    _seed(conn, item="healthsafetyonjo00albe_3", leaf=5, printed=None, pid="healthsafetyonjo00albe_3#5:0")
    c = citation.citation_for(conn, "healthsafetyonjo00albe_3#5:0")
    assert c is not None and c.printed_page is None
    assert c.deep_link == "https://archive.org/details/healthsafetyonjo00albe_3/page/n5"
    conn.close()


def test_verifier_pass():
    conn = db.init_db(":memory:")
    _seed(conn, pid="itemA#0:0")
    chk = citation.verify_citation(conn, "itemA#0:0", ["itemA#0:0", "other"])
    assert (chk.exists, chk.in_evidence, chk.resolves, chk.ok) == (True, True, True, True)
    assert chk.deep_link == "https://archive.org/details/itemA/page/n0"
    conn.close()


def test_verifier_fail_missing_passage():
    conn = db.init_db(":memory:")
    chk = citation.verify_citation(conn, "nope", ["nope"])
    assert chk.exists is False and chk.ok is False and chk.deep_link is None
    conn.close()


def test_verifier_fail_not_in_evidence():
    conn = db.init_db(":memory:")
    _seed(conn, pid="itemA#0:0")
    chk = citation.verify_citation(conn, "itemA#0:0", ["someone_else"])
    assert chk.exists is True and chk.in_evidence is False and chk.ok is False
    conn.close()


def test_verifier_fail_unresolvable_page():
    # Dangling page_id -> resolves False. FK off (plain connect) to insert it.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema.create_schema(conn)
    conn.execute("INSERT INTO items (item_id) VALUES ('itemA')")
    conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, text) "
                 "VALUES ('itemA#g:0','itemA','ghost',0,'x')")
    conn.commit()
    chk = citation.verify_citation(conn, "itemA#g:0", ["itemA#g:0"])
    assert chk.exists is True and chk.resolves is False and chk.deep_link is None and chk.ok is False
    conn.close()


def test_verify_citations_batch():
    conn = db.init_db(":memory:")
    _seed(conn, pid="itemA#0:0")
    res = citation.verify_citations(conn, ["itemA#0:0", "missing"], ["itemA#0:0"])
    assert [r.ok for r in res] == [True, False]
    conn.close()
