"""Phase 7 labeling-assist tests. Hermetic: stub retriever, in-memory db, no model."""
from __future__ import annotations

import json
from pathlib import Path

from archive_debugger.eval import assist, label, questions, store
from archive_debugger.ingest import db


def _hit(pid, text="tuberculosis sanatorium treatment beds", jur="alberta", year=1985, ocr=0.95, leaf=0):
    return {"passage_id": pid, "score": 0.9, "text": text, "year": year, "jurisdiction": jur,
            "doc_type": "other", "ocr_quality": ocr, "title": "T", "leaf_index": leaf,
            "printed_page": "1", "page_deep_link": f"https://archive.org/details/itemA/page/n{leaf}"}


class StubRetriever:
    def __init__(self, canned):
        self.canned = canned

    def search(self, query, filters=None, top_k=20):
        return self.canned.get(query, [])[:top_k]

    def close(self):
        pass


def _seed_q(conn, qid, text, qtype="factual", filters=None):
    questions.insert_questions(conn, [{"qid": qid, "text": text, "qtype": qtype, "filters": filters or {}}])


def _seed_passages(conn, pids):
    conn.execute("INSERT OR IGNORE INTO items (item_id) VALUES ('itemA')")
    conn.execute("INSERT OR IGNORE INTO pages (page_id,item_id,leaf_index) VALUES ('p0','itemA',0)")
    for pid in pids:
        conn.execute("INSERT OR IGNORE INTO passages (passage_id,item_id,page_id,leaf_index,text) "
                     "VALUES (?,?,?,?,?)", (pid, "itemA", "p0", 0, "x"))
    conn.commit()


def _read(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_ws(path, summary, candidates):
    with Path(path).open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "summary", **summary}) + "\n")
        for c in candidates:
            fh.write(json.dumps({"kind": "candidate", **c}) + "\n")


def test_worksheet_all_fields_no_score(tmp_path):
    conn = db.init_db(":memory:")
    _seed_q(conn, "q1", "tuberculosis sanatorium treatment beds")
    retr = StubRetriever({"tuberculosis sanatorium treatment beds": [_hit("pA")]})
    out = assist.run(conn=conn, retriever=retr, top_n=30, out_path=tmp_path / "ws.jsonl")
    recs = _read(out)
    summary = next(r for r in recs if r["kind"] == "summary")
    cand = next(r for r in recs if r["kind"] == "candidate")
    for f in ("qid", "passage_id", "rank", "year", "jurisdiction", "doc_type", "ocr_quality",
              "title", "leaf_index", "printed_page", "deep_link", "excerpt",
              "proposed_relevance", "reason"):
        assert f in cand
    assert "score" not in cand and "score" not in summary
    assert set(summary) >= {"qid", "text", "qtype", "filters", "proposed_answerable", "reason"}
    conn.close()


def test_assist_writes_zero_gold(tmp_path):
    conn = db.init_db(":memory:")
    _seed_q(conn, "q1", "tuberculosis treatment beds")
    retr = StubRetriever({"tuberculosis treatment beds": [_hit("pA")]})
    assist.run(conn=conn, retriever=retr, top_n=30, out_path=tmp_path / "ws.jsonl")
    assert conn.execute("SELECT COUNT(*) FROM eval_labels").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eval_question_gold").fetchone()[0] == 0
    conn.close()


def test_proposed_answerable_positive_and_negative(tmp_path):
    conn = db.init_db(":memory:")
    _seed_q(conn, "q1", "tuberculosis sanatorium treatment beds")
    _seed_q(conn, "qa", "covid-19 pandemic response in 2020", qtype="abstention_probe")
    retr = StubRetriever({
        "tuberculosis sanatorium treatment beds": [_hit("pA", text="tuberculosis sanatorium treatment beds")],
        "covid-19 pandemic response in 2020": [_hit("pB", text="covid pandemic response 2020")],
    })
    out = assist.run(conn=conn, retriever=retr, top_n=30, out_path=tmp_path / "ws.jsonl")
    by_qid = {r["qid"]: r for r in _read(out) if r["kind"] == "summary"}
    assert by_qid["q1"]["proposed_answerable"] == 1      # on-topic, in-window
    assert by_qid["qa"]["proposed_answerable"] == 0      # post-2009 -> proposed 0 across candidates
    conn.close()


def test_from_worksheet_blank_writes_nothing(tmp_path):
    conn = db.init_db(":memory:")
    _seed_q(conn, "q1", "tuberculosis treatment")
    _seed_passages(conn, ["pA"])
    ws = tmp_path / "ws.jsonl"
    _write_ws(ws, {"qid": "q1", "text": "t", "qtype": "factual", "filters": {},
                   "proposed_answerable": 1, "reason": "x"},
              [{"qid": "q1", "passage_id": "pA", "rank": 1, "proposed_relevance": 1, "reason": "r",
                "excerpt": "e", "year": 1985, "jurisdiction": "alberta", "doc_type": "other",
                "ocr_quality": 0.9, "title": "T", "leaf_index": 0, "printed_page": "1", "deep_link": "u"}])
    ans = iter(["", ""])  # blank candidate answer, blank verdict
    label.run(conn=conn, worksheet=ws, prompt_fn=lambda p: next(ans), print_fn=lambda *a: None)
    assert store.get_labels(conn, "q1") == {}            # blank != accept proposal
    assert store.gold_verdict(conn, "q1") is None        # blank verdict -> no gold
    conn.close()


def _write_full_ws(path, qids, per_q=30):
    with Path(path).open("w", encoding="utf-8") as fh:
        for qid in qids:
            fh.write(json.dumps({"kind": "summary", "qid": qid, "text": "t", "qtype": "factual",
                                 "filters": {}, "proposed_answerable": 0, "reason": "x"}) + "\n")
            for rank in range(1, per_q + 1):
                fh.write(json.dumps({"kind": "candidate", "qid": qid, "passage_id": f"{qid}#p{rank}",
                                     "rank": rank, "proposed_relevance": 0, "reason": "r"}) + "\n")


def _seed_qids_and_passages(conn, qids, per_q=30):
    conn.execute("INSERT OR IGNORE INTO items (item_id) VALUES ('itemA')")
    conn.execute("INSERT OR IGNORE INTO pages (page_id,item_id,leaf_index) VALUES ('p0','itemA',0)")
    for qid in qids:
        questions.insert_questions(conn, [{"qid": qid, "text": "t", "qtype": "factual", "filters": {}}])
        for rank in range(1, per_q + 1):
            conn.execute("INSERT OR IGNORE INTO passages (passage_id,item_id,page_id,leaf_index,text) "
                         "VALUES (?,?,?,?,?)", (f"{qid}#p{rank}", "itemA", "p0", 0, "x"))
    conn.commit()


def test_apply_decisions_writes_full_grid_and_overwrites(tmp_path):
    conn = db.init_db(":memory:")
    qids = ["qA", "qB"]
    _seed_qids_and_passages(conn, qids)
    ws = tmp_path / "ws.jsonl"
    _write_full_ws(ws, qids)
    # pre-existing stale label on qA that apply must overwrite (revise semantics).
    store.write_label(conn, "qA", "qA#p1", 0)
    store.write_gold(conn, "qA", 0)
    dec = tmp_path / "dec.json"
    dec.write_text(json.dumps({"_meta": {"source": "test"},
                               "qA": {"v": "a", "r": [1, 3]},
                               "qB": {"v": "x", "r": []}}), encoding="utf-8")
    summary = label.apply_decisions(conn, ws, dec, expected_qids=2, candidates_per_q=30)
    assert summary == {"qids": 2, "labels": 60, "relevant": 2, "answerable": 1, "abstain": 1}
    assert conn.execute("SELECT COUNT(*) FROM eval_labels").fetchone()[0] == 60
    assert conn.execute("SELECT COUNT(*) FROM eval_labels WHERE qid='qA'").fetchone()[0] == 30
    assert {p for p, r in store.get_labels(conn, "qA").items() if r == 1} == {"qA#p1", "qA#p3"}
    assert all(r == 0 for r in store.get_labels(conn, "qB").values())
    assert store.gold_verdict(conn, "qA")["answerable"] == 1  # overwritten from 0 to 1
    assert store.gold_verdict(conn, "qB")["answerable"] == 0
    conn.close()


def test_apply_decisions_bad_rank_refuses_without_writing(tmp_path):
    conn = db.init_db(":memory:")
    qids = ["qA", "qB"]
    _seed_qids_and_passages(conn, qids)
    ws = tmp_path / "ws.jsonl"
    _write_full_ws(ws, qids)
    dec = tmp_path / "dec.json"
    dec.write_text(json.dumps({"qA": {"v": "a", "r": [99]}, "qB": {"v": "x", "r": []}}), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        label.apply_decisions(conn, ws, dec, expected_qids=2, candidates_per_q=30)
    # all-or-nothing: nothing written
    assert conn.execute("SELECT COUNT(*) FROM eval_labels").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eval_question_gold").fetchone()[0] == 0
    conn.close()


def test_apply_decisions_wrong_qid_count_refuses(tmp_path):
    conn = db.init_db(":memory:")
    _seed_qids_and_passages(conn, ["qA"])
    ws = tmp_path / "ws.jsonl"
    _write_full_ws(ws, ["qA"])
    dec = tmp_path / "dec.json"
    dec.write_text(json.dumps({"qA": {"v": "a", "r": [1]}}), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        label.apply_decisions(conn, ws, dec, expected_qids=50, candidates_per_q=30)
    assert conn.execute("SELECT COUNT(*) FROM eval_labels").fetchone()[0] == 0
    conn.close()


def test_from_worksheet_override_beats_proposal(tmp_path):
    conn = db.init_db(":memory:")
    _seed_q(conn, "q1", "tuberculosis treatment")
    _seed_passages(conn, ["pA", "pB"])
    ws = tmp_path / "ws.jsonl"
    _write_ws(ws, {"qid": "q1", "text": "t", "qtype": "factual", "filters": {},
                   "proposed_answerable": 0, "reason": "x"},
              [{"qid": "q1", "passage_id": "pA", "rank": 1, "proposed_relevance": 1, "reason": "r",
                "excerpt": "e", "year": 1985, "jurisdiction": "alberta", "doc_type": "other",
                "ocr_quality": 0.9, "title": "T", "leaf_index": 0, "printed_page": "1", "deep_link": "u"},
               {"qid": "q1", "passage_id": "pB", "rank": 2, "proposed_relevance": 0, "reason": "r",
                "excerpt": "e", "year": 1985, "jurisdiction": "alberta", "doc_type": "other",
                "ocr_quality": 0.9, "title": "T", "leaf_index": 0, "printed_page": "1", "deep_link": "u"}])
    # proposal: pA=relevant, pB=not, verdict=should-abstain. Jake overrides all three.
    ans = iter(["n", "r", "a"])
    label.run(conn=conn, worksheet=ws, prompt_fn=lambda p: next(ans), print_fn=lambda *a: None)
    assert store.get_labels(conn, "q1") == {"pA": 0, "pB": 1}     # overrides applied
    assert store.gold_verdict(conn, "q1")["answerable"] == 1      # override to answerable
    conn.close()
