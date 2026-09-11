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


# ---- Phase 13 switches ----------------------------------------------------


def _many(tmp_path: Path, n_items: int = 4, per_item: int = 4) -> RetrieveConfig:
    """n_items x per_item passages, all matching the query; item k is dated 1970+k."""
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    for k in range(n_items):
        item = f"item{k}"
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) VALUES (?,?,1,?,?,?,?,?)",
                     (item, item, 1970 + k, "1970s", "alberta", ["commission", "royal_commission", "other", "other"][k % 4], "u"))
        for leaf in range(per_item):
            text = "vaccination hospital programme" + (" in 1999 and 2001" if k == 0 and leaf == 0 else "")
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, has_text, section_class) VALUES (?,?,?,?,40,1,?)",
                         (f"{item}#{leaf}", item, leaf, str(leaf + 1), "front" if leaf == 0 else "body"))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES (?,?,?,?,0,40,?,4,'0.95')",
                         (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, text))
    conn.commit()
    conn.close()
    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    return RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub", embedding_model="stub", embedding_dim=64,
                          batch_size=8, candidates=50, rrf_k=60, downweights={"high": 1.0, "medium": 0.9, "low": 0.75},
                          doc_type_families={"commission": ["commission", "royal_commission"]})


def _search(cfg, query="vaccination hospital", **kw):
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        return r.search(query, **kw)
    finally:
        r.close()


def test_section_weight_multiplies_never_excludes():
    from archive_debugger.retrieve.fusion import apply_section_weight
    out = apply_section_weight({"a": 0.10, "b": 0.10, "c": 0.10}, {"a": "front", "b": None, "c": "back"},
                               {"front": 0.5, "body": 1.0, "back": 0.5})
    assert out == {"a": 0.05, "b": 0.10, "c": 0.05}


def test_section_demote_switch(tmp_path):
    from dataclasses import replace
    cfg = _many(tmp_path)
    off = _search(cfg, top_k=16)
    assert {h["section_class"] for h in off} == {"front", "body"}          # class always reported
    on = _search(replace(cfg, section_demote=True), top_k=16)
    assert len(on) == len(off) == 16                                        # nothing excluded
    assert all(h["section_class"] == "body" for h in on[:12])              # front pages sink to the bottom
    assert all(h["section_class"] == "front" for h in on[12:])


def test_fts_query_drops_stopwords_only_when_on(tmp_path):
    from dataclasses import replace
    cfg = _many(tmp_path)
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        assert r._fts_query("what did the report say about vaccination") == \
            '"what" OR "did" OR "the" OR "report" OR "say" OR "about" OR "vaccination"'
        r.cfg = replace(cfg, fts_drop_stopwords=True)
        assert r._fts_query("what did the report say about vaccination") == '"vaccination"'
        assert r._fts_query("what did they say") == '"what" OR "did" OR "they" OR "say"'   # all stopwords: fall back
    finally:
        r.close()


def test_doc_type_family_filter(tmp_path):
    from dataclasses import replace
    from archive_debugger.retrieve.filters import family_members
    fam = {"commission": ["commission", "royal_commission"]}
    assert family_members("royal_commission", fam) == ["commission", "royal_commission"]
    assert family_members("commission", fam) == ["commission", "royal_commission"]
    assert family_members("annual_report", fam) == []
    w, p = build_where(Filters(doc_type="royal_commission"), doc_type_families=fam)
    assert w == " AND i.doc_type_norm IN (?,?)" and p == ["commission", "royal_commission"]
    assert build_where(Filters(doc_type="royal_commission")) == (" AND i.doc_type_norm = ?", ["royal_commission"])
    cfg = _many(tmp_path)
    off = _search(cfg, filters=Filters(doc_type="commission"), top_k=16)
    assert {h["item_id"] for h in off} == {"item0"}
    on = _search(replace(cfg, doc_type_family_filter=True), filters=Filters(doc_type="commission"), top_k=16)
    assert {h["item_id"] for h in on} == {"item0", "item1"}


def test_per_item_cap(tmp_path):
    from collections import Counter
    from dataclasses import replace
    cfg = _many(tmp_path)
    off = Counter(h["item_id"] for h in _search(cfg, top_k=16))
    assert max(off.values()) == 4
    capped = _search(replace(cfg, per_item_cap=3), top_k=16)
    assert max(Counter(h["item_id"] for h in capped).values()) == 3 and len(capped) == 12
    assert len(_search(replace(cfg, per_item_cap=1), top_k=16)) == 4


def test_later_years_flag(tmp_path):
    from dataclasses import replace
    cfg = _many(tmp_path)
    off = {h["passage_id"]: h["later_years"] for h in _search(cfg, top_k=16)}
    assert set(off.values()) == {None}
    on = {h["passage_id"]: h["later_years"] for h in _search(replace(cfg, later_years_flag=True), top_k=16)}
    assert on["item0#0:0"] == [1999, 2001]                                 # item dated 1970; text mentions 1999, 2001
    assert on["item1#0:0"] is None


def test_retrieval_fingerprint_tracks_config_and_files(tmp_path):
    from dataclasses import replace
    from archive_debugger.api.cache import cache_key, retrieval_fingerprint
    cfg = _many(tmp_path)
    a = retrieval_fingerprint(cfg)
    assert a == retrieval_fingerprint(cfg)
    assert a != retrieval_fingerprint(replace(cfg, per_item_cap=3))
    with open(cfg.index_path, "ab") as fh:
        fh.write(b"\0")
    assert a != retrieval_fingerprint(cfg)                                 # size/mtime changed
    common = dict(question="q", filters=None, provider="stub", model="m", prompt_sha256="p", top_k=12, temperature=None)
    assert cache_key(**common, retrieval_sha256="x") != cache_key(**common, retrieval_sha256="y")


# ---- env path overrides (deployments mount data outside the repo) ---------


def test_env_overrides_config_paths(monkeypatch):
    from archive_debugger.retrieve.config import load_retrieve_config
    cfg_path = Path("config/pilot.toml")
    monkeypatch.setenv("CIVIC_DB_PATH", "/data/civic.db")
    monkeypatch.setenv("CIVIC_INDEX_PATH", "/data/index/vectors.db")
    cfg = load_retrieve_config(cfg_path)
    assert cfg.db_path == Path("/data/civic.db") and cfg.index_path == Path("/data/index/vectors.db")
    assert db.resolve_db_path(cfg_path) == Path("/data/civic.db")
    monkeypatch.delenv("CIVIC_DB_PATH")
    monkeypatch.delenv("CIVIC_INDEX_PATH")
    cfg = load_retrieve_config(cfg_path)
    assert cfg.db_path == Path("civic.db") and cfg.index_path == Path("index/vectors.db")   # config values
    assert db.resolve_db_path(cfg_path) == Path("civic.db")
    assert cfg.embedder == "fastembed"
    monkeypatch.setenv("CIVIC_EMBEDDER", "stub")
    assert load_retrieve_config(cfg_path).embedder == "stub"                                  # CI smoke override


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
