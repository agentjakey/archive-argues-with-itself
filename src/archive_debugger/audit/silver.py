"""Silver labels from two reference judges, the review queue, and the status rule.

A silver label exists for an item's check when both reference judges gave a verdict and the two
verdicts are the same class. Anything else (a disagreement, or a missing verdict) is a reference
disagreement and goes to the review queue first. The queue then takes a seeded random sample of the items
whose every check has a silver label, and then drafted-benchmark approval items, flagged ones first.

The status rule (Jake, 2026-11-01, amended 2026-11-02): until the review queue is labelled, results
are reported as agreement with reference labels and nothing earns AI-AUDITED. The queue's labels are
adjudicated reference labels: each item read and decided against its page, with a one-line reason.
Since 2026-11-02 they come from AI adjudication (source "adjudicated-ai"); no human has checked them
yet, and a label from the author, when there is one, takes the item's place. A check earns AI-AUDITED
only when the panel meets the judge bar against those labels and the silver labels' own error,
measured on the random agreed sample against the adjudicated labels, has an upper 95% Wilson bound of
at most 10%. The silver error is counted per item (an item is wrong when any of its silver labels
differs from the adjudicated one), so the unit is independent; with 40 items only zero errors keep the
bound under 10% (one error gives 0.129). Nothing here is ever called human-verified."""
from __future__ import annotations

import random
from collections import Counter
from typing import Optional

from archive_debugger.audit import calibration, panel, prompts

SILVER_FORMAT = 1
QUEUE_FORMAT = 1
SILVER_ERROR_MAX = 0.10
QUEUE_MAX = 80
RANDOM_AGREED = 40
APPROVAL_MAX = 20


def silver_for(item: dict, refs: dict) -> dict:
    """{check: {"silver": class or None, "votes": {judge: class or None}}} for one item. refs maps
    each reference judge's name to its judgment record for the item (or None)."""
    out = {}
    for check in prompts.KIND_CHECKS[prompts.kind_of(item)]:
        votes = {name: panel.vote(rec, check) for name, rec in sorted(refs.items())}
        values = list(votes.values())
        agreed = len(values) >= 2 and values[0] is not None and all(v == values[0] for v in values)
        out[check] = {"silver": values[0] if agreed else None, "votes": votes}
    return out


def build(items: list, judgments: dict, references: tuple) -> list:
    """Silver rows for every item. judgments maps (item_id, judge) to a judgment record."""
    rows = []
    for it in items:
        refs = {name: judgments.get((it["item_id"], name)) for name in references}
        checks = silver_for(it, refs)
        rows.append({"format": SILVER_FORMAT, "item_id": it["item_id"], "kind": prompts.kind_of(it),
                     "collection": it.get("collection"), "category": it.get("category"),
                     "references": list(references), "checks": checks,
                     "agreed": all(v["silver"] is not None for v in checks.values()),
                     "labeler": "silver", "review": "reference-judges"})
    return rows


def silver_labels(rows: list) -> dict:
    """{check: {item_id: class}} for the checks that have a silver label."""
    out = {c: {} for c in prompts.ALL_CHECKS}
    for row in rows:
        for check, v in row["checks"].items():
            if v["silver"] is not None:
                out[check][row["item_id"]] = v["silver"]
    return out


def approval_flagged(item_id: str, silver_row: Optional[dict], panel_row: Optional[dict]) -> bool:
    """A drafted benchmark item is flagged when the references disagree on it, either reference
    rejects it, or the panel rejected it or left it to a person."""
    if silver_row is not None:
        for v in silver_row["checks"].values():
            if v["silver"] != "pass":
                return True
    if panel_row is not None:
        if panel_row.get("human_queue"):
            return True
        if any(v.get("final") not in (None, "pass") for v in panel_row.get("checks", {}).values()):
            return True
    return False


def queue(kit_rows: list, approval_items: list, approval_silver: dict, approval_panel: dict, seed: int, *,
          max_items: int = QUEUE_MAX, random_agreed: int = RANDOM_AGREED, approval_max: int = APPROVAL_MAX) -> tuple:
    """The review queue: every reference disagreement on the kit first, then a seeded random
    `random_agreed` of the agreed kit items, then up to `approval_max` approval items, flagged ones
    first, never more than `max_items` in all. kit_rows are silver rows for the kit. Returns
    (ordered [(item_id, section)], counts). When the disagreements alone would leave no room for the
    random sample, the disagreements are cut to make room for it and the cut is reported: without the
    random sample the silver labels' error cannot be measured at all."""
    rng = random.Random(f"queue:{seed}")
    disagreements = sorted(r["item_id"] for r in kit_rows if not r["agreed"])
    agreed = sorted(r["item_id"] for r in kit_rows if r["agreed"])
    sample = sorted(rng.sample(agreed, min(random_agreed, len(agreed))))
    room_for_disagreements = max_items - len(sample)
    cut = 0
    if len(disagreements) > room_for_disagreements:
        cut = len(disagreements) - room_for_disagreements
        disagreements = sorted(rng.sample(disagreements, room_for_disagreements))
    order = [(i, "reference_disagreement") for i in disagreements] + [(i, "random_agreed") for i in sample]
    room = max(0, min(approval_max, max_items - len(order)))
    flagged = [it["item_id"] for it in approval_items
               if approval_flagged(it["item_id"], approval_silver.get(it["item_id"]), approval_panel.get(it["item_id"]))]
    unflagged = [it["item_id"] for it in approval_items if it["item_id"] not in set(flagged)]
    rng.shuffle(unflagged)
    picked = (sorted(flagged) + unflagged)[:room]
    order += [(i, "benchmark_approval_flagged" if i in set(flagged) else "benchmark_approval") for i in picked]
    counts = dict(Counter(section for _, section in order))
    counts.update({"disagreements_total": len(disagreements) + cut, "disagreements_cut": cut,
                   "agreed_total": len(agreed), "approval_flagged_total": len(flagged)})
    return order, counts


def silver_error(kit_rows: list, author: dict, sample_ids: list) -> dict:
    """The silver labels' error against the queue's adjudicated labels on the random agreed sample,
    per item and per check. author is {check: {item_id: class}}."""
    by_id = {r["item_id"]: r for r in kit_rows}
    item_errors = 0
    n_items = 0
    per_check: dict = {}
    for item_id in sample_ids:
        row = by_id.get(item_id)
        if row is None:
            continue
        labelled = [(c, v["silver"], author.get(c, {}).get(item_id)) for c, v in row["checks"].items()]
        labelled = [(c, s, a) for c, s, a in labelled if a is not None]
        if not labelled:
            continue
        n_items += 1
        wrong = False
        for c, s, a in labelled:
            pc = per_check.setdefault(c, {"n": 0, "errors": 0, "binary_errors": 0})
            pc["n"] += 1
            if s != a:
                pc["errors"] += 1
                wrong = True
            if calibration.binary(s) != calibration.binary(a):
                pc["binary_errors"] += 1
        item_errors += wrong
    for pc in per_check.values():
        pc["rate"] = pc["errors"] / pc["n"] if pc["n"] else None
        pc["wilson"] = calibration.wilson(pc["errors"], pc["n"])
    upper = calibration.wilson(item_errors, n_items)[1] if n_items else None
    return {"items": n_items, "item_errors": item_errors, "rate": item_errors / n_items if n_items else None,
            "wilson": calibration.wilson(item_errors, n_items), "per_check": per_check,
            "meets": upper is not None and upper <= SILVER_ERROR_MAX, "max_upper": SILVER_ERROR_MAX}


def status(check: str, panel_bar: dict, queue_labelled: bool, silver: Optional[dict]) -> dict:
    """The audit status a check may claim. Before the review queue is labelled, never AI-AUDITED."""
    if not queue_labelled:
        return {"check": check, "status": "AGREEMENT-WITH-REFERENCE-ONLY", "ai_audited": False,
                "why": "the review queue is not labelled yet: results are agreement with reference labels"}
    reasons = []
    if not panel_bar.get("meets"):
        reasons.append("panel misses the bar: " + "; ".join(panel_bar.get("reasons") or []))
    if silver is None or not silver.get("meets"):
        upper = None if silver is None else silver["wilson"][1]
        reasons.append(f"silver error upper bound {upper if upper is None else round(upper, 3)} over {SILVER_ERROR_MAX}")
    return {"check": check, "status": "AI-AUDITED" if not reasons else "NOT-AI-AUDITED",
            "ai_audited": not reasons,
            "why": "; ".join(reasons) or "panel meets the bar against adjudicated labels and the silver error bound holds"}
