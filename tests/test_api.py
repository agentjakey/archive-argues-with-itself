"""Phase 10a read-only API tests. Hermetic: TestClient, stub LLM, stub embedder, temp db."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from archive_debugger.api.app import create_app
from archive_debugger.eval import questions, store
from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM
from archive_debugger.ingest import db
from archive_debugger.retrieve import citation, index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder

CFG = Path("config/pilot.toml")
TEXT = "vaccination hospital programme"


def _retriever(tmp_path, items, *, seed_questions=None):
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
                         batch_size=8, candidates=10, rrf_k=60, downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    return search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg), seed


def test_health(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta")])
    with TestClient(create_app(CFG, retriever=r, provider="stub", web_dist=tmp_path / "nodist")) as c:
        body = c.get("/health").json()
    assert body["status"] == "ok" and body["provider"] == "stub"


def test_ask_evidence_ordered_year_asc_undated_last(tmp_path):
    r, _ = _retriever(tmp_path, [("late", 1990, "ontario"), ("early", 1975, "federal"), ("nodate", None, "alberta")])
    with TestClient(create_app(CFG, retriever=r, provider="stub", web_dist=tmp_path / "nodist")) as c:
        ev = c.post("/ask", json={"question": "vaccination hospital"}).json()["evidence"]
    years = [e["year"] for e in ev]
    dated = [y for y in years if y is not None]
    assert dated == sorted(dated) and years[-1] is None and years == dated + [None] * years.count(None)
    row = ev[0]
    for k in ("deep_link", "page_thumb", "page_image", "embed_url", "snippet", "bm25_rank", "dense_rank", "cited"):
        assert k in row
    assert row["page_thumb"] == citation.page_thumb(row["item_id"], row["leaf_index"])
    assert row["embed_url"] == citation.embed_url(row["item_id"], row["leaf_index"])


def test_ask_cited_flags_match_verified_citations(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    hits = r.search("vaccination hospital", top_k=12)
    cited = hits[0]["passage_id"]
    llm = StubLLM(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=[cited])]))
    with TestClient(create_app(CFG, retriever=r, provider="stub", llm=llm, web_dist=tmp_path / "nodist")) as c:
        body = c.post("/ask", json={"question": "vaccination hospital", "model": "claude-sonnet-5"}).json()
    verified = {v["passage_id"] for v in body["answer"]["verified_citations"]}
    assert verified == {cited} and body["answer"]["abstained"] is False
    assert {e["passage_id"] for e in body["evidence"] if e["cited"]} == verified
    gen = body["answer"]["generation"]
    assert gen["model"] == "claude-sonnet-5" and gen["provider"] == "stub" and gen["temperature"] is None
    assert len(gen["prompt_sha256"]) == 64


def test_ask_abstention_shape(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    with TestClient(create_app(CFG, retriever=r, provider="stub", web_dist=tmp_path / "nodist")) as c:
        body = c.post("/ask", json={"question": "covid vaccination"}).json()   # 'covid' uncovered
    a = body["answer"]
    assert a["abstained"] is True and a["abstention_text"].startswith("the record here is thin")
    assert a["coverage"]["uncovered_terms"] == ["covid"] and a["sentences"] == []
    assert body["evidence"] and not any(e["cited"] for e in body["evidence"])


def test_examples_with_gold(tmp_path):
    r, seed = _retriever(tmp_path, [("a", 1985, "alberta")], seed_questions=[("qA", 1), ("qB", 0), ("qC", None)])
    with TestClient(create_app(CFG, retriever=r, provider="stub", seed_path=seed, web_dist=tmp_path / "nodist")) as c:
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
    with TestClient(create_app(CFG, retriever=r, provider="stub", web_dist=dist)) as c:
        assert c.get("/").text == "<h1>app</h1>"
        assert c.get("/asset.js").text == "1;"
        assert c.get("/some/client/route").text == "<h1>app</h1>"   # fallback
        assert c.get("/health").json()["status"] == "ok"          # API routes still win
