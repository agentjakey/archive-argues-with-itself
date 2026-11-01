"""Silver labels, the author's queue and the status rule (audit/silver.py)."""
from __future__ import annotations

from archive_debugger.audit import silver


def sentence(i):
    return {"item_id": f"c:q{i}:s1", "kind": "sentence", "collection": "c"}


def answer(i):
    return {"item_id": f"c:q{i}:answer", "kind": "answer", "collection": "c"}


def rec(**checks):
    return {"verdicts": {c: {"verdict": v, "reason": ""} for c, v in checks.items()}}


def test_a_silver_label_needs_both_references_to_agree_and_both_to_answer():
    refs = ("a", "b")
    items = [sentence(1), sentence(2), answer(3)]
    j = {("c:q1:s1", "a"): rec(supports="pass", in_scope="pass"), ("c:q1:s1", "b"): rec(supports="pass", in_scope="fail"),
         ("c:q2:s1", "a"): rec(supports="partial", in_scope="pass"),
         ("c:q3:answer", "a"): rec(answers="partial"), ("c:q3:answer", "b"): rec(answers="partial")}
    rows = {r["item_id"]: r for r in silver.build(items, j, refs)}
    assert rows["c:q1:s1"]["checks"]["supports"]["silver"] == "pass"
    assert rows["c:q1:s1"]["checks"]["in_scope"]["silver"] is None and not rows["c:q1:s1"]["agreed"]
    assert rows["c:q2:s1"]["checks"]["supports"]["silver"] is None            # one reference missing
    assert rows["c:q3:answer"]["agreed"] and rows["c:q3:answer"]["checks"]["answers"]["silver"] == "partial"
    labels = silver.silver_labels(list(rows.values()))
    assert labels["supports"] == {"c:q1:s1": "pass"} and labels["answers"] == {"c:q3:answer": "partial"}


def kit_rows(n_agreed, n_disagree):
    rows = []
    for i in range(n_agreed):
        rows.append({"item_id": f"a{i:03d}", "agreed": True, "checks": {"supports": {"silver": "pass"}}})
    for i in range(n_disagree):
        rows.append({"item_id": f"d{i:03d}", "agreed": False, "checks": {"supports": {"silver": None}}})
    return rows


def test_the_queue_puts_disagreements_first_then_40_random_agreed_then_approval_flagged_first():
    approval = [{"item_id": f"b{i}"} for i in range(30)]
    approval_silver = {"b3": {"checks": {"label_correct": {"silver": "fail"}}}}
    approval_panel = {"b7": {"human_queue": ["well_formed"], "checks": {}}}
    order, counts = silver.queue(kit_rows(100, 12), approval, approval_silver, approval_panel, seed=1)
    sections = [s for _, s in order]
    assert len(order) == 72 and sections[:12] == ["reference_disagreement"] * 12
    assert sections[12:52] == ["random_agreed"] * 40
    assert [i for i, s in order if s == "benchmark_approval_flagged"] == ["b3", "b7"]
    assert counts["benchmark_approval_flagged"] == 2 and counts["benchmark_approval"] == 18
    again, _ = silver.queue(kit_rows(100, 12), approval, approval_silver, approval_panel, seed=1)
    assert again == order


def test_the_queue_never_exceeds_80_and_keeps_room_for_the_random_sample():
    order, counts = silver.queue(kit_rows(100, 60), [{"item_id": "b1"}], {}, {}, seed=2)
    assert len(order) == 80
    assert counts["random_agreed"] == 40 and counts["reference_disagreement"] == 40
    assert counts["disagreements_total"] == 60 and counts["disagreements_cut"] == 20
    assert "benchmark_approval" not in counts


def test_silver_error_is_per_item_and_only_zero_errors_in_40_meet_the_bound():
    rows = kit_rows(40, 0)
    ids = [r["item_id"] for r in rows]
    author = {"supports": {i: "pass" for i in ids}}
    clean = silver.silver_error(rows, author, ids)
    assert clean["item_errors"] == 0 and clean["meets"] and clean["wilson"][1] < 0.10
    author["supports"]["a000"] = "partial"
    one = silver.silver_error(rows, author, ids)
    assert one["item_errors"] == 1 and not one["meets"] and round(one["wilson"][1], 3) == 0.129


def test_nothing_is_ai_audited_before_the_author_labels_and_both_conditions_are_needed():
    good_bar = {"meets": True, "reasons": []}
    ok_silver = {"meets": True, "wilson": (0.0, 0.08)}
    bad_silver = {"meets": False, "wilson": (0.0, 0.13)}
    assert silver.status("supports", good_bar, False, ok_silver)["status"] == "AGREEMENT-WITH-REFERENCE-ONLY"
    assert silver.status("supports", good_bar, True, ok_silver)["ai_audited"]
    assert not silver.status("supports", good_bar, True, bad_silver)["ai_audited"]
    assert not silver.status("supports", {"meets": False, "reasons": ["kappa"]}, True, ok_silver)["ai_audited"]
