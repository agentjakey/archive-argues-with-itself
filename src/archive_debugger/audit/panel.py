"""The panel's final verdict for each check (docs/formats/audit.md).

For each item and each of SUPPORTS, ANSWERS and IN SCOPE: when the two panel judges agree, that is
the verdict. When they disagree, or either judgment is missing, the item goes to the escalation
judge; if it sides with one of the two panel judges, that is the verdict. Otherwise the check goes
to the human queue and has no verdict until a person decides it. VALID comes from the gates."""
from __future__ import annotations

from typing import Optional

from archive_debugger.audit.prompts import CHECKS

PANEL_VERSION = 1


def vote(judgment: Optional[dict], check: str) -> Optional[str]:
    if not judgment or not judgment.get("verdicts"):
        return None
    return judgment["verdicts"][check]["verdict"]


def needs_escalation(first: Optional[dict], second: Optional[dict]) -> bool:
    return any(vote(first, c) is None or vote(first, c) != vote(second, c) for c in CHECKS)


def decide(item_id: str, gate: dict, panel_judges: tuple, judgments: dict, escalation: Optional[dict]) -> dict:
    """judgments: {judge name: judgment record} for the two panel judges; escalation: the escalation
    judge's record, or None when it was not needed or not run."""
    a_name, b_name = panel_judges
    a, b = judgments.get(a_name), judgments.get(b_name)
    checks = {}
    for check in CHECKS:
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
    return {"item_id": item_id, "panel_version": PANEL_VERSION, "valid": gate["valid"], "flags": gate["flags"],
            "checks": checks, "human_queue": [c for c in CHECKS if checks[c]["route"] == "human"]}
