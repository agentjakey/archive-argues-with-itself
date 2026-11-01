"""The panel's final verdict for each check (docs/formats/audit.md).

A sentence item carries SUPPORTS and IN SCOPE, an answer item ANSWERS. For each of the item's
checks: when the two panel judges agree, that is the verdict. When they disagree, or either judgment
is missing, the item goes to the escalation judge; if it sides with one of the two panel judges, that
is the verdict. Otherwise the check goes to the human queue and has no verdict until a person decides
it. VALID comes from the gates.

Leniency review: in every run the escalation judge also reads a seeded random share of the items
the panel agreed to pass. It changes no verdict. When it disagrees on more than the configured share
of that sample for a check, the run flags the panel as too lenient on that check."""
from __future__ import annotations

import math
import random
from typing import Optional

from archive_debugger.audit.calibration import wilson
from archive_debugger.audit.prompts import KIND_CHECKS, kind_of

PANEL_VERSION = 2


def vote(judgment: Optional[dict], check: str) -> Optional[str]:
    if not judgment or not judgment.get("verdicts") or check not in judgment["verdicts"]:
        return None
    return judgment["verdicts"][check]["verdict"]


def needs_escalation(first: Optional[dict], second: Optional[dict], checks: tuple) -> bool:
    return any(vote(first, c) is None or vote(first, c) != vote(second, c) for c in checks)


def decide(item: dict, gate: dict, panel_judges: tuple, judgments: dict, escalation: Optional[dict]) -> dict:
    """judgments: {judge name: judgment record} for the two panel judges; escalation: the escalation
    judge's record, or None when it was not needed or not run."""
    a_name, b_name = panel_judges
    a, b = judgments.get(a_name), judgments.get(b_name)
    checks = {}
    for check in KIND_CHECKS[kind_of(item)]:
        va, vb = vote(a, check), vote(b, check)
        votes = {a_name: va, b_name: vb}
        if va is not None and va == vb:
            checks[check] = {"final": va, "route": "agree", "votes": votes}
            continue
        ve = vote(escalation, check)
        if escalation is not None:
            votes["escalation"] = ve
        if ve is not None and ve in (va, vb):
            checks[check] = {"final": ve, "route": "escalated", "votes": votes}
        else:
            checks[check] = {"final": None, "route": "human", "votes": votes}
    return {"item_id": item["item_id"], "kind": kind_of(item), "panel_version": PANEL_VERSION, "valid": gate["valid"],
            "flags": gate["flags"], "checks": checks, "human_queue": [c for c in checks if checks[c]["route"] == "human"]}


def agreed_passes(decision: dict) -> list:
    return [c for c, v in decision["checks"].items() if v["route"] == "agree" and v["final"] == "pass"]


def review_sample(decisions: list, share: float, seed: str) -> list:
    """The item ids of a seeded random `share` (rounded up) of the items with at least one agreed
    pass. The seed is the run id, so a resumed run reviews the same items."""
    ids = sorted(d["item_id"] for d in decisions if agreed_passes(d))
    if not ids or share <= 0:
        return []
    count = min(len(ids), max(1, math.ceil(share * len(ids) - 1e-9)))
    return sorted(random.Random(f"leniency:{seed}").sample(ids, count))


def leniency(decisions: list, reviews: dict, lenient_above: float) -> dict:
    """{check: summary} of the escalation judge's verdicts on the reviewed agreed passes. reviews maps
    item_id to the escalation judgment. A check is flagged when the escalation judge did not pass more
    than lenient_above of the reviewed agreed passes it judged."""
    out = {}
    for d in decisions:
        review = reviews.get(d["item_id"])
        if review is None:
            continue
        for check in agreed_passes(d):
            v = vote(review, check)
            row = out.setdefault(check, {"reviewed": 0, "no_verdict": 0, "disagree": 0, "item_ids": []})
            if v is None:
                row["no_verdict"] += 1
                continue
            row["reviewed"] += 1
            if v != "pass":
                row["disagree"] += 1
                row["item_ids"].append(d["item_id"])
    for check, row in out.items():
        n = row["reviewed"]
        row["rate"] = row["disagree"] / n if n else None
        row["wilson"] = wilson(row["disagree"], n)
        row["too_lenient"] = bool(n) and row["disagree"] / n > lenient_above
    return out
