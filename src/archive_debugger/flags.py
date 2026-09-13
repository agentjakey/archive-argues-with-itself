"""Harm-adjacent topic flagging (additive, N5-safe).

Reads only the served-evidence fields already on each /ask evidence row (title, snippet,
year) plus nothing else; it touches neither retrieval nor the abstention gate. It is
computed ON SERVE and never stored in the answer cache, so it fires identically for a
cached answer, a real abstention, and the offline limited-mode state, keyed on the
retrieved record rather than on whether generation ran.

Matching is deliberately conservative on ambiguous terms (a public-health corpus is full
of "blood pressure" and "hearing aids"), because over-flagging a benign result is its own
harm; but the bias on specific terms is toward recall, because missing a flagged result is
worse than a terse note. Tune by editing TOPIC_SIGNALS: each value is a list of regex
patterns matched case-insensitively against a row's title + snippet.
"""
from __future__ import annotations

import re
from typing import Optional

# Editable topic config: topic key -> signal patterns (regex, case-insensitive), matched
# against each served evidence row's title + snippet. Prefer specific multi-word phrases
# over bare ambiguous words. Seeded for Jacob to tune and finalize.
TOPIC_SIGNALS: dict[str, list[str]] = {
    "tainted-blood-krever": [
        r"\bkrever\b",
        r"\btainted blood\b",
        r"\bcontaminated blood\b",
        r"\bblood system\b",
        r"\bblood supply\b",
        r"\bblood-borne\b",
    ],
    "coerced-sterilization-indigenous": [
        r"\bsexual sterilization\b",
        r"\bsterilization act\b",
        r"\b(?:forced|coerced|involuntary|compulsory)\s+steriliz\w*",
        r"\beugenic\w*",
    ],
    "residential-school-health": [
        r"\bresidential school\w*",
        r"\bindian residential\b",
    ],
    "early-hiv-aids": [
        r"\bhiv\b",
        r"\bhiv/aids\b",
        r"\bacquired immune deficiency\b",
        r"\bacquired immunodeficiency\b",
        r"\bhuman immunodeficiency\b",
        # "aids" in the epidemic sense, excluding the common benign compounds a health
        # corpus is full of (hearing/teaching/visual/first/study/learning aids).
        r"(?<!hearing )(?<!teaching )(?<!visual )(?<!first )(?<!study )(?<!learning )\baids\b",
    ],
}

# Exactly the verified lines Jacob supplied (both 24/7); he re-verifies the week of the event.
CRISIS_LINES: list[dict] = [
    {"name": "National Indian Residential School Crisis Line", "number": "1-866-925-4419"},
    {"name": "Hope for Wellness Help Line", "number": "1-855-242-3310"},
]

# The whole retrieved record is shown in the evidence trail, so by default any shown row
# counts (recall-biased: missing a flagged result is worse than a terse note). Set True to
# narrow to the rows the model actually saw (in_prompt), if full-pool matching flags too
# many tangential results for the venue.
MATCH_IN_PROMPT_ONLY = False

_COMPILED = {t: [re.compile(p, re.IGNORECASE) for p in pats] for t, pats in TOPIC_SIGNALS.items()}


def _haystack(row: dict) -> str:
    return f"{row.get('title') or ''} {row.get('snippet') or ''}"


def _row_topics(row: dict) -> list[str]:
    hay = _haystack(row)
    return [t for t, pats in _COMPILED.items() if any(p.search(hay) for p in pats)]


def _rows(evidence: list[dict]):
    for row in evidence:
        if MATCH_IN_PROMPT_ONLY and not row.get("in_prompt", True):
            continue
        yield row


def flagged_topics(evidence: list[dict]) -> list[str]:
    """Topic keys whose signal appears in any served evidence row's title or snippet."""
    found: set[str] = set()
    for row in _rows(evidence):
        found.update(_row_topics(row))
    return sorted(found)


def detect(evidence: list[dict]) -> Optional[dict]:
    """The `flagged` field for the /ask response, or None. `year` is the earliest year
    among the rows that matched a topic, for the client's year-aware contextual note. The
    visitor-facing note text is rendered client-side from topics + year (not baked here)."""
    topics: set[str] = set()
    years: list[int] = []
    for row in _rows(evidence):
        matched = _row_topics(row)
        if matched:
            topics.update(matched)
            if row.get("year") is not None:
                years.append(int(row["year"]))
    if not topics:
        return None
    return {"topics": sorted(topics), "year": min(years) if years else None, "crisis_lines": CRISIS_LINES}
