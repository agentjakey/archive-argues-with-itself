"""Phase 6 hybrid-retrieval tests. Hermetic: stub embedder, tiny fixture, no model."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from archive_debugger.ingest import db, schema
from archive_debugger.retrieve import index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder, make_embedder
from archive_debugger.retrieve.filters import Filters, build_where, period_predicate
from archive_debugger.retrieve.fusion import apply_downweight, rrf


# ---- RRF ------------------------------------------------------------------


def test_rrf_fusion_order():
    fused = rrf([["a", "b", "c"], ["b", "c", "a"]], k=60)
    order = sorted(fused, key=lambda p: fused[p], reverse=True)
    assert order == ["b", "a", "c"]  # b high in both; a beats c on ranks


def test_rrf_rewards_agreement():
    fused = rrf([["x", "y"], ["x", "z"]], k=60)
    assert fused["x"] > fused["y"] and fused["x"] > fused["z"]


# ---- filters --------------------------------------------------------------


def test_period_predicates():
    assert period_predicate("undated") == ("i.dated = 0", [])
    assert period_predicate("pre-1960") == ("i.dated = 1 AND i.year < 1960", [])
    assert period_predicate("post-2009") == ("i.dated = 1 AND i.year > 2009", [])
    assert period_predicate("1980s") == ("i.dated = 1 AND i.year BETWEEN ? AND ?", [1980, 1989])


def test_filter_each_in_isolation():
    assert build_where(Filters(jurisdiction="federal")) == (" AND i.jurisdiction_norm = ?", ["federal"])
    assert build_where(Filters(doc_type="annual_report")) == (" AND i.doc_type_norm = ?", ["annual_report"])
    w, p = build_where(Filters(min_ocr=0.5))
    assert w == " AND CAST(p.ocr_quality AS REAL) >= ?" and p == [0.5]


def test_filters_compose():
    w, p = build_where(Filters(period="1980s", jurisdiction="alberta"))
    assert w == " AND i.dated = 1 AND i.year BETWEEN ? AND ? AND i.jurisdiction_norm = ?"
    assert p == [1980, 1989, "alberta"]


# ---- down-weight ----------------------------------------------------------


def test_downweight_reorders_pair():
    weights = {"high": 1.0, "medium": 0.9, "low": 0.75}
    fused = {"low_but_high_rank": 0.10, "high_quality": 0.09}
    quality = {"low_but_high_rank": 0.2, "high_quality": 0.9}  # low vs high bucket
    final = apply_downweight(fused, quality, weights)
    assert final["high_quality"] > final["low_but_high_rank"]  # 0.09 vs 0.075


# ---- deterministic smoke test over a tiny fixture -------------------------


def _fixture(tmp_path: Path) -> RetrieveConfig:
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    conn.executemany(
        "INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("itemA", "Alberta health", 1, 1985, "1980s", "alberta", "annual_report", "https://archive.org/details/itemA"),
            ("itemB", "Ontario labour", 1, 1975, "1970s", "ontario", "other", "https://archive.org/details/itemB"),
        ],
    )
    conn.executemany(
        "INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, has_text) VALUES (?,?,?,?,?,?)",
        [("itemA#0", "itemA", 0, "1", 40, 1), ("itemB#0", "itemB", 0, "1", 40, 1)],
    )
    conn.executemany(
        "INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("itemA#0:0", "itemA", "itemA#0", 0, 0, 40, "vaccination hospital sante alberta", 4, "0.95"),
            ("itemB#0:0", "itemB", "itemB#0", 0, 0, 40, "occupational labour safety ontario", 4, "0.95"),
        ],
    )
    conn.commit()
    conn.close()

    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    return RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub",
                          embedding_model="stub", embedding_dim=64, batch_size=8,
                          candidates=10, rrf_k=60,
                          downweights={"high": 1.0, "medium": 0.9, "low": 0.75})


def test_retrieval_smoke_expected_ids(tmp_path):
    cfg = _fixture(tmp_path)
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        hits = r.search("vaccination hospital", top_k=2)
        assert hits[0]["passage_id"] == "itemA#0:0"
        assert hits[0]["page_deep_link"] == "https://archive.org/details/itemA/page/n0"
    finally:
        r.close()


def test_retrieval_filter_restricts(tmp_path):
    cfg = _fixture(tmp_path)
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        hits = r.search("labour safety", filters=Filters(jurisdiction="alberta"), top_k=5)
        assert all(h["jurisdiction"] == "alberta" for h in hits)
        assert "itemB#0:0" not in {h["passage_id"] for h in hits}
    finally:
        r.close()


def test_provenance_missing_page_raises_lookuperror(tmp_path):
    # A retrieved passage whose page row is missing must fail loud, not shorten
    # the result set. Build the fixture with FK enforcement off so the dangling
    # page_id can be inserted deliberately.
    civ = tmp_path / "civic.db"
    conn = sqlite3.connect(str(civ))
    schema.create_schema(conn)
    conn.execute("INSERT INTO items (item_id, title, dated, year, decade, details_url) VALUES ('itemA','A',1,1985,'1980s','u')")
    conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, has_text) VALUES ('itemA#0','itemA',0,'1',10,1)")
    conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES ('itemA#0:0','itemA','itemA#0',0,0,10,'zzz filler',2,'0.95')")
    # Dangling: real item, page_id resolves to nothing -> provenance must raise.
    conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES ('ghost:0','itemA','ghost#0',0,0,20,'quarantine directive uniqueterm',3,'0.95')")
    conn.commit()
    conn.close()

    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    cfg = RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub",
                         embedding_model="stub", embedding_dim=64, batch_size=8,
                         candidates=10, rrf_k=60,
                         downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        with pytest.raises(LookupError):
            r.search("quarantine directive uniqueterm", top_k=5)
    finally:
        r.close()


# ---- CI guard: real model never imported ----------------------------------


def test_stub_factory_returns_stub():
    assert isinstance(make_embedder("stub", "unused", 64), StubEmbedder)


def test_search_exposes_per_leg_ranks(tmp_path):
    cfg = _fixture(tmp_path)
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        hits = r.search("vaccination hospital", top_k=2)
        assert {"bm25_rank", "dense_rank"} <= set(hits[0])
        assert any(h["bm25_rank"] is not None for h in hits)  # the FTS leg matched
    finally:
        r.close()


def test_importing_retrieve_does_not_import_fastembed():
    code = ("import archive_debugger.retrieve.embed, archive_debugger.retrieve.search, sys; "
            "assert 'fastembed' not in sys.modules, 'fastembed imported at module load'")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
