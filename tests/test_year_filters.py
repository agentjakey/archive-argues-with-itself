"""Year range, "as of year" and issuer filters: the SQL predicate, the cache key, the engine's request
paths, and a real search over a small corpus."""
from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.api import cache as answer_cache
from archive_debugger.generate.cli import build_filters
from archive_debugger.ingest import db
from archive_debugger.retrieve import index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder
from archive_debugger.retrieve.filters import Filters, build_where

ITEMS = [
    ("old", "Alberta Health", 1, 1974),
    ("mid", "Alberta Health", 1, 1985),
    ("new", "Health Canada (federal health portfolio)", 1, 1999),
    ("undated", "Alberta Health", 0, None),
]


def _corpus(tmp_path: Path) -> search.Retriever:
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    for item_id, issuer, dated, year in ITEMS:
        decade = f"{(year // 10) * 10}s" if year else None
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, "
                     "issuer_norm, details_url) VALUES (?,?,?,?,?,?,?,?,?)",
                     (item_id, f"Hospital report {item_id}", dated, year, decade, "alberta", "annual_report", issuer,
                      f"https://archive.org/details/{item_id}"))
        conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, has_text) "
                     "VALUES (?,?,?,?,?,?)", (f"{item_id}#0", item_id, 0, "1", 40, 1))
        conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, "
                     "token_count, ocr_quality) VALUES (?,?,?,?,?,?,?,?,?)",
                     (f"{item_id}#0:0", item_id, f"{item_id}#0", 0, 0, 40, "hospital insurance enrollment report", 4,
                      "0.95"))
    conn.commit()
    conn.close()
    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    cfg = RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub", embedding_model="stub", embedding_dim=64,
                         batch_size=8, candidates=10, rrf_k=60, downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    return search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)


def _items(retriever, filters: Filters) -> set:
    return {h["item_id"] for h in retriever.search("hospital insurance", filters=filters, top_k=10)}


def test_predicates():
    assert build_where(Filters(year_from=1980)) == (" AND i.dated = 1 AND i.year >= ?", [1980])
    assert build_where(Filters(year_to=1990)) == (" AND i.dated = 1 AND i.year <= ?", [1990])
    assert build_where(Filters(as_of_year=1990)) == (" AND i.dated = 1 AND i.year <= ?", [1990])
    # year_to and as_of_year together: the earlier bound wins, one clause.
    assert build_where(Filters(year_to=1995, as_of_year=1980)) == (" AND i.dated = 1 AND i.year <= ?", [1980])
    assert build_where(Filters(issuer="Alberta Health")) == (" AND i.issuer_norm = ?", ["Alberta Health"])


def test_search_applies_each_filter(tmp_path):
    r = _corpus(tmp_path)
    try:
        assert _items(r, Filters()) == {"old", "mid", "new", "undated"}
        assert _items(r, Filters(year_from=1980)) == {"mid", "new"}
        assert _items(r, Filters(year_to=1985)) == {"old", "mid"}
        assert _items(r, Filters(as_of_year=1980)) == {"old"}
        assert _items(r, Filters(year_from=1980, year_to=1990)) == {"mid"}
        assert _items(r, Filters(issuer="Alberta Health")) == {"old", "mid", "undated"}
        assert _items(r, Filters(issuer="Alberta Health", year_from=1980)) == {"mid"}
        assert _items(r, Filters(year_from=2000)) == set()
    finally:
        r.close()


def test_canonical_year_accepts_whole_numbers_only():
    y = answer_cache.canonical_year
    assert y(1974) == y("1974") == y(" 1974 ") == y(1974.0) == 1974
    for bad in (True, 1974.5, "1974.0", "74", "nineteen", "1974a", 999, 2101, "0999", None, [1974]):
        with pytest.raises((ValueError, TypeError)):
            y(bad)


def test_cache_key_filters():
    f = answer_cache.canonical_filters
    assert f({"year_from": 1974, "year_to": "1999"}) == {"year_from": "1974", "year_to": "1999"}
    assert f({"as_of_year": "", "issuer": " Alberta Health "}) == {"issuer": "Alberta Health"}
    # A request without the new filters keys exactly as before they existed.
    assert f({"jurisdiction": "alberta"}) == {"jurisdiction": "alberta"}
    with pytest.raises(ValueError):
        f({"year_from": "soon"})
    applied = answer_cache.applied_filters({"year_from": " 1980 ", "as_of_year": 1990.0, "issuer": "x"})
    assert applied == {"year_from": 1980, "as_of_year": 1990, "issuer": "x"}
    built = build_filters(applied)
    assert (built.year_from, built.year_to, built.as_of_year, built.issuer) == (1980, None, 1990, "x")
    assert build_filters({}).year_from is None and build_filters({}).issuer is None


def test_engine_paths_take_the_filters(tmp_path):
    from fastapi.testclient import TestClient
    from archive_debugger.api.app import create_app
    repo = Path(__file__).resolve().parent.parent
    r = _corpus(tmp_path)
    app = create_app(repo / "config" / "pilot.toml", retriever=r, llm=None, provider="stub", load_env=False,
                     cache_path=tmp_path / "cache" / "answers.db", web_dist=tmp_path / "nodist")
    with TestClient(app) as c:
        body = c.get("/ask", params={"q": "hospital insurance", "year_from": "1980", "issuer": "Alberta Health",
                                     "provider": "stub", "evidence_only": 1}).json()
        assert {e["item_id"] for e in body["evidence"]} == {"mid"}
        body = c.post("/ask", json={"question": "hospital insurance", "filters": {"as_of_year": 1980},
                                    "provider": "stub", "evidence_only": True}).json()
        assert {e["item_id"] for e in body["evidence"]} == {"old"}
        bad = c.post("/ask", json={"question": "hospital insurance", "filters": {"year_to": "later"},
                                   "provider": "stub"})
        assert bad.status_code == 422 and "bad filter" in bad.json()["detail"]
        cov = c.get("/coverage", params={"q": "hospital insurance", "year_to": "1985"})
        assert cov.status_code == 200
