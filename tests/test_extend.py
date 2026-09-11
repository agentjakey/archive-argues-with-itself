"""Phase 13 pooled-labels extension: worksheet holds only unjudged candidates with
their candidate ranks; apply is additive and refuses to overwrite a label."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from archive_debugger.eval import extend, questions, store
from archive_debugger.ingest import db
from archive_debugger.retrieve import index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder


def _fixture(tmp_path: Path):
    civ, vectors = tmp_path / "civic.db", tmp_path / "vectors.db"
    conn = db.init_db(str(civ))
    for k in range(3):
        item = f"it{k}"
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) "
                     "VALUES (?,?,1,?,?, 'alberta', 'other', 'u')", (item, item, 1980 + k, "1980s"))
        for leaf in range(2):
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, has_text, section_class) VALUES (?,?,?,1,'body')",
                         (f"{item}#{leaf}", item, leaf))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) "
                         "VALUES (?,?,?,?,0,30,'vaccination hospital programme',3,'0.95')", (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf))
    questions.insert_questions(conn, [{"qid": "q001", "text": "vaccination hospital", "qtype": "factual", "filters": {}}])
    store.write_label(conn, "q001", "it0#0:0", 1)      # already judged
    store.write_label(conn, "q001", "it1#0:0", 0)
    store.write_gold(conn, "q001", 1)
    conn.commit()
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    cfg = RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub", embedding_model="stub", embedding_dim=64,
                         batch_size=8, candidates=50, rrf_k=60, downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=extend.candidate_config(cfg))
    return conn, r


def test_worksheet_holds_only_unjudged_with_candidate_ranks(tmp_path):
    conn, r = _fixture(tmp_path)
    try:
        records, stats = extend.build_records(conn, r, top_n=20)
    finally:
        r.close()
    cands = [x for x in records if x["kind"] == "candidate"]
    assert stats["candidates"] == 4 and stats["questions_with_new"] == 1
    assert {c["passage_id"] for c in cands} == {"it0#1:0", "it1#1:0", "it2#0:0", "it2#1:0"}
    assert all(1 <= c["rank"] <= 6 for c in cands) and len({c["rank"] for c in cands}) == 4   # candidate ranks kept
    assert records[0]["kind"] == "summary" and "proposed_relevance" in cands[0]              # Phase 7 format
    assert not any("switch" in k for c in cands for k in c)                                  # blind to switches
    conn.close()


def test_apply_is_additive_and_refuses_overwrite(tmp_path):
    conn, r = _fixture(tmp_path)
    try:
        records, _ = extend.build_records(conn, r, top_n=20)
    finally:
        r.close()
    ws = tmp_path / "ws.jsonl"
    ws.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
    cands = sorted((x for x in records if x["kind"] == "candidate"), key=lambda c: c["rank"])
    first, last = cands[0]["rank"], cands[-1]["rank"]
    with pytest.raises(ValueError, match="more than one of r/u/n"):
        extend.apply_extension(conn, ws, {"q001": {"r": [first], "u": [first]}})
    out = extend.apply_extension(conn, ws, {"q001": {"r": [first], "u": [last]}})
    assert out == {"qids": 1, "labels": 3, "relevant": 1, "uncertain_unlabeled": 1, "verdict_changes": []}
    labels = store.get_labels(conn, "q001")
    assert labels["it0#0:0"] == 1 and labels["it1#0:0"] == 0                                # originals untouched
    assert len(labels) == 5 and labels[cands[0]["passage_id"]] == 1
    assert cands[-1]["passage_id"] not in labels                                            # uncertain stays unjudged
    with pytest.raises(ValueError, match="additive only"):
        extend.apply_extension(conn, ws, {"q001": {"r": []}})                                 # second apply clashes
    # Batch 2 shape: explicit r/n lists label only those ranks (the earlier uncertain one).
    out2 = extend.apply_extension(conn, ws, {"q001": {"r": [last], "n": []}})
    assert out2["labels"] == 1 and out2["relevant"] == 1 and store.get_labels(conn, "q001")[cands[-1]["passage_id"]] == 1
    with pytest.raises(ValueError, match="additive only"):
        extend.apply_extension(conn, ws, {"q001": {"r": [], "n": [last]}})                    # already decided
    with pytest.raises(ValueError, match="not in the extension worksheet"):
        extend.apply_extension(conn, ws, {"q999": {"r": []}})
    conn.close()


def test_apply_records_verdict_change_only_when_asked(tmp_path):
    conn, r = _fixture(tmp_path)
    try:
        records, _ = extend.build_records(conn, r, top_n=20)
    finally:
        r.close()
    ws = tmp_path / "ws.jsonl"
    ws.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
    out = extend.apply_extension(conn, ws, {"q001": {"r": [], "v": "x"}})
    assert out["verdict_changes"] == [{"qid": "q001", "from": 1, "to": 0}]
    assert store.gold_verdict(conn, "q001")["answerable"] == 0
    conn.close()
