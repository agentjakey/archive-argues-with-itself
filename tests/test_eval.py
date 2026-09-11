"""Phase 7 eval tests. Hermetic: no model, no index, no network."""
from __future__ import annotations

import subprocess
import sys

import pytest

from archive_debugger.eval import label, metrics, questions, store
from archive_debugger.ingest import db


# ---- metrics --------------------------------------------------------------


def test_recall_at_k():
    ranked = ["p1", "p2", "p3", "p4"]
    gold = {"p1", "p3"}
    assert metrics.recall_at_k(ranked, gold, 2) == 0.5
    assert metrics.recall_at_k(ranked, gold, 4) == 1.0


def test_recall_empty_gold_is_none():
    assert metrics.recall_at_k(["p1"], set(), 5) is None


def test_ndcg_at_k_known_value():
    ranked = ["p1", "p2", "p3", "p4"]
    gold_rel = {"p1": 1, "p3": 1}
    # dcg = 1/log2(2) + 1/log2(4) = 1.5 ; idcg = 1/log2(2) + 1/log2(3) = 1.6309...
    assert metrics.ndcg_at_k(ranked, gold_rel, 4) == pytest.approx(1.5 / 1.6309297, rel=1e-4)


def test_ndcg_all_relevant_is_one():
    assert metrics.ndcg_at_k(["p1", "p2"], {"p1": 1, "p2": 1}, 2) == pytest.approx(1.0)


def test_ndcg_empty_gold_is_none():
    assert metrics.ndcg_at_k(["p1"], {}, 10) is None


def test_abstention_correct():
    ranked = ["p1", "p2"]
    thin = {}                       # no relevant passages judged
    has = {"p1": 1}                 # one relevant
    assert metrics.abstention_correct(ranked, thin, 0, 2, 1) is True   # should-abstain + thin
    assert metrics.abstention_correct(ranked, has, 0, 2, 1) is False   # should-abstain + evidence
    assert metrics.abstention_correct(ranked, has, 1, 2, 1) is True    # answerable + evidence


# ---- harness scaffolding --------------------------------------------------


class StubRetriever:
    def __init__(self, canned):
        self.canned = canned

    def search(self, query, filters=None, top_k=20):
        return self.canned.get(query, [])[:top_k]

    def close(self):
        pass


def _hit(pid, item="itemA", leaf=0):
    return {"passage_id": pid, "score": 0.5, "text": "excerpt", "year": 1985,
            "jurisdiction": "alberta", "doc_type": "other", "ocr_quality": 0.95,
            "title": "T", "leaf_index": leaf, "printed_page": "1",
            "page_deep_link": f"https://archive.org/details/{item}/page/n{leaf}"}


def _seed_one(conn):
    questions.insert_questions(conn, [
        {"qid": "q001", "text": "alberta health", "topic": "t", "qtype": "factual", "filters": {}}])


def _seed_passages(conn, pids):
    # eval_labels.passage_id FKs passages(passage_id), which FKs pages+items, so a
    # labelable passage needs a real item/page/passage chain.
    conn.execute("INSERT OR IGNORE INTO items (item_id) VALUES ('itemA')")
    conn.execute("INSERT OR IGNORE INTO pages (page_id, item_id, leaf_index) VALUES ('p0','itemA',0)")
    for pid in pids:
        conn.execute("INSERT OR IGNORE INTO passages (passage_id, item_id, page_id, leaf_index, text) "
                     "VALUES (?,?,?,?,?)", (pid, "itemA", "p0", 0, "x"))
    conn.commit()


def _scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def _quiet(*_a, **_k):
    return None


# ---- harness tests --------------------------------------------------------


def test_harness_writes_labels_and_gold():
    conn = db.init_db(":memory:")
    _seed_one(conn)
    _seed_passages(conn, ["pA", "pB"])
    retr = StubRetriever({"alberta health": [_hit("pA"), _hit("pB")]})
    label.run(conn=conn, retriever=retr, top_n=30,
              prompt_fn=_scripted(["r", "n", "a"]), print_fn=_quiet)
    assert store.get_labels(conn, "q001") == {"pA": 1, "pB": 0}
    assert store.gold_verdict(conn, "q001")["answerable"] == 1
    conn.close()


def test_harness_resumes_skips_labeled():
    conn = db.init_db(":memory:")
    _seed_one(conn)
    _seed_passages(conn, ["pA"])
    retr = StubRetriever({"alberta health": [_hit("pA")]})
    label.run(conn=conn, retriever=retr, top_n=30,
              prompt_fn=_scripted(["r", "a"]), print_fn=_quiet)

    def boom(_prompt):
        raise AssertionError("prompt must not be called for an already-labeled question")

    # A second run must skip q001 and never consume a prompt.
    label.run(conn=conn, retriever=retr, top_n=30, prompt_fn=boom, print_fn=_quiet)
    assert store.get_labels(conn, "q001") == {"pA": 1}
    conn.close()


def test_harness_skip_writes_no_label():
    conn = db.init_db(":memory:")
    _seed_one(conn)
    _seed_passages(conn, ["pA", "pB"])
    retr = StubRetriever({"alberta health": [_hit("pA"), _hit("pB")]})
    # pA -> 's' (skip), pB -> '' (empty); neither may write an eval_labels row.
    label.run(conn=conn, retriever=retr, top_n=30,
              prompt_fn=_scripted(["s", "", "a"]), print_fn=_quiet)
    assert store.get_labels(conn, "q001") == {}
    assert store.gold_verdict(conn, "q001")["answerable"] == 1
    conn.close()


def test_harness_revise_overwrites():
    conn = db.init_db(":memory:")
    _seed_one(conn)
    _seed_passages(conn, ["pA"])
    retr = StubRetriever({"alberta health": [_hit("pA")]})
    label.run(conn=conn, retriever=retr, top_n=30,
              prompt_fn=_scripted(["r", "a"]), print_fn=_quiet)
    assert store.get_labels(conn, "q001") == {"pA": 1}
    # --revise re-opens the labeled question; the new answer overwrites.
    label.run(conn=conn, retriever=retr, top_n=30, revise=True,
              prompt_fn=_scripted(["n", "x"]), print_fn=_quiet)
    assert store.get_labels(conn, "q001") == {"pA": 0}
    assert store.gold_verdict(conn, "q001")["answerable"] == 0
    conn.close()


# ---- loader + report ------------------------------------------------------


def test_questions_qtype_optional_and_validated():
    conn = db.init_db(":memory:")
    questions.insert_questions(conn, [{"qid": "n1", "text": "t", "qtype": None, "filters": {}}])
    assert store.get_question(conn, "n1")["qtype"] is None
    with pytest.raises(ValueError):
        questions.insert_questions(conn, [{"qid": "n2", "text": "t", "qtype": "bogus"}])
    conn.close()


def test_report_partial_and_abstention_leakage():
    conn = db.init_db(":memory:")
    questions.insert_questions(conn, [
        {"qid": "qf", "text": "alberta health", "qtype": "factual", "filters": {}},
        {"qid": "qa", "text": "covid 2020", "qtype": "abstention_probe", "filters": {}},
        {"qid": "qu", "text": "unlabeled", "qtype": "factual", "filters": {}},
    ])
    # qf: answerable, pA relevant. qa: should-abstain, one leaked relevant mark. qu: unlabeled.
    _seed_passages(conn, ["pA", "pX"])
    store.write_label(conn, "qf", "pA", 1)
    store.write_gold(conn, "qf", 1)
    store.write_label(conn, "qa", "pX", 1)
    store.write_gold(conn, "qa", 0)
    from archive_debugger.eval import report
    retr = StubRetriever({"alberta health": [_hit("pA")], "covid 2020": [_hit("pX")]})
    rep = report.evaluate(conn, retr, recall_ks=[5, 10, 20], ndcg_k=10, min_relevant=1, top_n=30)
    assert rep["labeled"] == 2 and rep["total"] == 3            # partial: qu excluded
    assert "abstention_correct" not in rep["aggregate"]         # no abstention rate reported
    assert rep["abstention_leakage"] == [{"qid": "qa", "n_surfaced": 30, "n_marked_relevant": 1}]
    conn.close()


# ---- CI guard -------------------------------------------------------------


def test_importing_eval_does_not_import_fastembed():
    code = ("import archive_debugger.eval.label, archive_debugger.eval.report, "
            "archive_debugger.eval.metrics, sys; "
            "assert 'fastembed' not in sys.modules, 'fastembed imported at module load'")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
