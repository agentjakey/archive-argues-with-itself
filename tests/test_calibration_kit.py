"""The calibration kit's order and batches, and the form's label checks (scripts/v2)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "v2" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kit = load("calibration_kit")
form = load("calibration_form")


def sentence(qid, n):
    return {"item_id": f"c:{qid}:s{n}", "kind": "sentence", "collection": "c", "qid": qid, "sentence_no": n}


def answer(qid):
    return {"item_id": f"c:{qid}:answer", "kind": "answer", "collection": "c", "qid": qid}


def test_the_kit_goes_answer_by_answer_and_pulls_the_must_haves_forward():
    qids = [f"q{n:02d}" for n in range(40)]
    order = [sentence(q, n) for n in (2, 1) for q in qids]           # stratified order, sentences out of order
    must = frozenset({"c:q39:s1", "c:q38:s2"})
    rows = kit.order_by_answer(order, [answer(q) for q in qids] + [answer("q99")], must, must_by=20)
    assert rows[0]["kind"] == "answer" and rows[1]["item_id"] == f"c:{rows[0]['qid']}:s1"
    positions = {r["item_id"]: n for n, r in enumerate(rows)}
    assert positions["c:q39:s1"] < 30 and positions["c:q38:s2"] < 30
    assert rows[-1]["item_id"] == "c:q99:answer"                       # an answer with no sampled sentence goes last
    for r in rows:
        if r["kind"] == "sentence":
            assert positions[f"c:{r['qid']}:answer"] < positions[r["item_id"]]


def test_a_batch_never_splits_an_answer():
    rows = []
    for q in range(30):
        rows.append(answer(f"q{q}"))
        rows.extend(sentence(f"q{q}", n) for n in range(1, 4))
    kit.assign_batches(rows, batch_sentences=10)
    for q in range(30):
        assert len({r["kit_batch"] for r in rows if r["qid"] == f"q{q}"}) == 1
    assert [r["kit_position"] for r in rows] == list(range(1, len(rows) + 1))
    assert max(r["kit_batch"] for r in rows) == 8                       # 90 sentences, batches close at 12


def test_the_form_takes_the_labels_of_the_item_unit_only():
    kinds = {"c:q1:s1": "sentence", "c:q1:answer": "answer"}
    assert form.valid_label({"item_id": "c:q1:s1", "supports": "pass", "in_scope": "unclear"}, kinds) is None
    assert form.valid_label({"item_id": "c:q1:answer", "answers": "partial"}, kinds) is None
    assert "answers" in form.valid_label({"item_id": "c:q1:answer", "supports": "pass"}, kinds)
    assert "not labelled" in form.valid_label({"item_id": "c:q1:s1", "supports": "pass", "in_scope": "pass",
                                               "answers": "pass"}, kinds)
    assert form.valid_label({"item_id": "c:q9:s1", "supports": "pass", "in_scope": "pass"}, kinds) == "unknown item"
    row = form.label_row({"item_id": "c:q1:answer", "answers": "fail", "note": "x"}, "answer", "first", "v")
    assert row["answers"] == "fail" and "supports" not in row and row["review"] == "author-reviewed"
