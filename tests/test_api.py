"""Phase 10 read-only API tests. Hermetic: TestClient, stub LLM, stub embedder, temp db."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from archive_debugger.api.app import MISSING_KEY, create_app
from archive_debugger.eval import questions, store
from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM
from archive_debugger.ingest import db
from archive_debugger.retrieve import citation, index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder

CFG = Path("config/pilot.toml")
TEXT = "vaccination hospital programme"


def _retriever(tmp_path, items, *, seed_questions=None, candidates=10):
    """items: [(item_id, year_or_None, jurisdiction)]; two passages each, all matching the query.
    seed_questions: optional [(qid, gold_or_None)] -> eval_questions (+gold) and a seed file."""
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    for item, year, jur in items:
        dated = 0 if year is None else 1
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) VALUES (?,?,?,?,?,?,?,?)",
                     (item, item, dated, year, None if year is None else f"{(year // 10) * 10}s", jur, "other", "u"))
        for leaf in (0, 1):
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, has_text) VALUES (?,?,?,?,1)",
                         (f"{item}#{leaf}", item, leaf, str(leaf + 1)))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES (?,?,?,?,0,30,?,3,'0.95')",
                         (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, TEXT))
    seed = None
    if seed_questions:
        questions.insert_questions(conn, [{"qid": q, "text": "vaccination hospital", "qtype": "factual", "filters": {}}
                                          for q, _ in seed_questions])
        for q, gold in seed_questions:
            if gold is not None:
                store.write_gold(conn, q, gold)
        seed = tmp_path / "seed.jsonl"
        seed.write_text("".join(json.dumps({"qid": q, "text": "vaccination hospital", "qtype": "factual",
                                            "filters": {"jurisdiction": "alberta"}}) + "\n"
                                for q, _ in seed_questions), encoding="utf-8")
    conn.commit()
    conn.close()
    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    cfg = RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub", embedding_model="stub", embedding_dim=64,
                         batch_size=8, candidates=candidates, rrf_k=60, downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    return search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg), seed


def _app(tmp_path, r, **kw):
    kw.setdefault("provider", "stub")
    kw.setdefault("web_dist", tmp_path / "nodist")
    kw.setdefault("cache_path", tmp_path / "cache" / "answers.db")
    return create_app(CFG, retriever=r, load_env=False, **kw)


def test_health_with_corpus_facts(tmp_path):
    r, _ = _retriever(tmp_path, [("late", 1990, "ontario"), ("early", 1975, "federal"), ("nodate", None, "alberta")])
    with TestClient(_app(tmp_path, r)) as c:
        body = c.get("/health").json()
    assert body["status"] == "ok" and body["provider"] == "stub"
    corpus = body["corpus"]
    assert corpus["items"] == 3 and corpus["passages"] == 6 and corpus["passages_undated"] == 2
    assert corpus["undated_share"] == round(2 / 6, 4)
    assert corpus["window"] == {"min_year": 1975, "max_year": 1990}            # true dated span
    assert corpus["pilot_window"] == {"min_year": 1960, "max_year": 2009}     # config binning window


def test_ask_is_cached_and_nocache_bypasses(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    hits = r.search("vaccination hospital", top_k=12)
    llm = StubLLM(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=[hits[0]["passage_id"]])]))
    with TestClient(_app(tmp_path, r, llm=llm)) as c:
        first = c.post("/ask", json={"question": "vaccination hospital"}).json()
        second = c.post("/ask", json={"question": "vaccination hospital"}).json()
        fresh = c.post("/ask", json={"question": "vaccination hospital", "nocache": True}).json()
        other = c.post("/ask", json={"question": "vaccination hospital", "filters": {"jurisdiction": "ontario"}}).json()
        via_get = c.get("/ask", params={"q": "vaccination hospital"}).json()
    assert first["answer"]["cached"] is None
    assert second["answer"]["cached"] is not None and "created_at" in second["answer"]["cached"]
    assert second["answer"]["text"] == first["answer"]["text"] and second["evidence"] == first["evidence"]
    assert fresh["answer"]["cached"] is None                                  # nocache recomputed
    assert other["answer"]["cached"] is None                                  # different filters, different key
    assert other["answer"]["abstained"]                                       # 2 ontario passages < min_passages: thin, no model call
    assert via_get["answer"]["cached"] is not None                            # GET shares the cache
    assert llm.calls == 2                                                     # first and nocache only
    assert (tmp_path / "cache" / "answers.db").exists()


def test_trail_pool_marks_what_the_model_saw(tmp_path):
    items = [(f"i{k}", 1970 + k, "alberta") for k in range(8)]          # 16 passages > top_k 12
    r, _ = _retriever(tmp_path, items, candidates=50)
    with TestClient(_app(tmp_path, r)) as c:
        body = c.post("/ask", json={"question": "vaccination hospital"}).json()
    rows = body["evidence"]
    assert len(rows) == 16                                                # the whole pool is the trail
    assert sum(row["in_prompt"] for row in rows) == 12                    # exactly top_k reached the model
    assert body["answer"]["coverage"]["n_passages"] == 12
    assert all(row["section_class"] == "body" and row["later_years"] is None for row in rows)


def test_cache_path_from_env(tmp_path, monkeypatch):
    target = tmp_path / "volume" / "cache" / "answers.db"
    monkeypatch.setenv("CIVIC_CACHE_PATH", str(target))
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta")])
    app = create_app(CFG, retriever=r, load_env=False, provider="stub", web_dist=tmp_path / "nodist")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
    assert target.exists()                                                    # created under the env path


def test_coverage_endpoint(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario"), ("c", None, "federal")])
    with TestClient(_app(tmp_path, r)) as c:
        cov = c.get("/coverage", params={"q": "vaccination covid", "jurisdiction": "alberta"}).json()
        again = c.get("/coverage", params={"q": "vaccination covid", "jurisdiction": "alberta"}).json()
    assert cov["salient_terms"] == ["vaccination", "covid"]
    lanes = {row["decade"]: row for row in cov["by_decade"]}
    assert lanes["1980s"]["terms"] == {"vaccination": 2, "covid": 0} and lanes["1980s"]["passages"] == 2
    assert lanes["1990s"]["passages"] == 0                                    # filtered out (ontario)
    assert all(row["terms"]["covid"] == 0 for row in cov["by_decade"])
    assert again == cov                                                       # in-process cache is stable


def test_ask_evidence_ordered_year_asc_undated_last(tmp_path):
    r, _ = _retriever(tmp_path, [("late", 1990, "ontario"), ("early", 1975, "federal"), ("nodate", None, "alberta")])
    with TestClient(_app(tmp_path, r)) as c:
        ev = c.post("/ask", json={"question": "vaccination hospital"}).json()["evidence"]
    years = [e["year"] for e in ev]
    dated = [y for y in years if y is not None]
    assert dated == sorted(dated) and years[-1] is None and years == dated + [None] * years.count(None)
    row = ev[0]
    for k in ("deep_link", "page_thumb", "page_image", "embed_url", "snippet", "bm25_rank", "dense_rank", "cited"):
        assert k in row
    assert row["page_thumb"] == citation.page_thumb(row["item_id"], row["leaf_index"])
    assert row["embed_url"] == citation.embed_url(row["item_id"], row["leaf_index"])


def test_ask_get_permalink_matches_post(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    with TestClient(_app(tmp_path, r)) as c:
        got = c.get("/ask", params={"q": "vaccination hospital", "jurisdiction": "alberta"}).json()
        posted = c.post("/ask", json={"question": "vaccination hospital", "filters": {"jurisdiction": "alberta"}}).json()
    assert [e["passage_id"] for e in got["evidence"]] == [e["passage_id"] for e in posted["evidence"]]
    assert all(e["jurisdiction"] == "alberta" for e in got["evidence"])
    assert got["answer"]["abstained"] == posted["answer"]["abstained"]


def test_ask_cited_flags_match_verified_citations(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    hits = r.search("vaccination hospital", top_k=12)
    cited = hits[0]["passage_id"]
    llm = StubLLM(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=[cited])]))
    with TestClient(_app(tmp_path, r, llm=llm)) as c:
        body = c.post("/ask", json={"question": "vaccination hospital", "model": "claude-sonnet-5"}).json()
    verified = {v["passage_id"] for v in body["answer"]["verified_citations"]}
    assert verified == {cited} and body["answer"]["abstained"] is False
    assert {e["passage_id"] for e in body["evidence"] if e["cited"]} == verified
    gen = body["answer"]["generation"]
    assert gen["model"] == "claude-sonnet-5" and gen["provider"] == "stub" and gen["temperature"] is None
    assert len(gen["prompt_sha256"]) == 64


def test_ask_abstention_shape(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    with TestClient(_app(tmp_path, r)) as c:
        body = c.post("/ask", json={"question": "covid vaccination"}).json()   # 'covid' uncovered
    a = body["answer"]
    assert a["abstained"] is True and a["abstention_text"].startswith("the record here is thin")
    assert a["coverage"]["uncovered_terms"] == ["covid"] and a["sentences"] == []
    assert body["evidence"] and not any(e["cited"] for e in body["evidence"])


def test_ask_503_when_no_key_for_anthropic(tmp_path, monkeypatch):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with TestClient(_app(tmp_path, r, provider="anthropic")) as c:
        res = c.post("/ask", json={"question": "vaccination hospital"})
    assert res.status_code == 503 and res.json() == {"error": MISSING_KEY}


def test_ask_502_on_llm_failure(tmp_path):
    class Boom:
        def draft(self, system, user):
            raise RuntimeError("boom")

    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    with TestClient(_app(tmp_path, r, llm=Boom())) as c:
        res = c.post("/ask", json={"question": "vaccination hospital"})
    assert res.status_code == 502 and res.json() == {"error": "RuntimeError: boom"}


def test_examples_with_gold(tmp_path):
    r, seed = _retriever(tmp_path, [("a", 1985, "alberta")], seed_questions=[("qA", 1), ("qB", 0), ("qC", None)])
    with TestClient(_app(tmp_path, r, seed_path=seed)) as c:
        ex = c.get("/examples").json()
    by = {e["qid"]: e for e in ex}
    assert set(by) == {"qA", "qB", "qC"}
    assert by["qA"]["gold"] == "answerable" and by["qB"]["gold"] == "abstain" and by["qC"]["gold"] is None
    assert by["qA"]["filters"] == {"jurisdiction": "alberta"} and by["qA"]["text"] == "vaccination hospital"


def test_spa_fallback_serves_index_when_dist_exists(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>app</h1>", encoding="utf-8")
    (dist / "asset.js").write_text("1;", encoding="utf-8")
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta")])
    with TestClient(_app(tmp_path, r, web_dist=dist)) as c:
        assert c.get("/").text == "<h1>app</h1>"
        assert c.get("/asset.js").text == "1;"
        assert c.get("/some/client/route").text == "<h1>app</h1>"   # fallback
        assert c.get("/health").json()["status"] == "ok"          # API routes still win
        assert c.get("/ask", params={"q": "vaccination hospital"}).status_code == 200  # GET /ask beats the catch-all
