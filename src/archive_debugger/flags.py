"""Harm-adjacent topic flagging (additive, N5-safe).

Reads only the served-evidence fields already on each /ask evidence row (title, snippet,
year, and the in_prompt / cited markers); it touches neither retrieval nor the abstention
gate. It is computed ON SERVE and never stored in the answer cache, so it fires identically
for a cached answer, a real abstention, and the offline limited-mode state.

Two design rules keep it proportionate:

- Answer-basis, not the whole pool. A topic counts only when it appears in a row the
  visitor actually reads as the answer basis: a row sent to the model (in_prompt) or cited.
  A tangential retrieved-pool row the model never used does not trigger a flag. For an
  abstention or the offline limited-mode state no generation ran, but in_prompt still marks
  the top_k shown as the record, so the flag still fires on that path.

- Precision over recall on the care-critical topics, because a false positive here is worse
  than a miss. In particular, "sterilization" in this corpus is overwhelmingly the benign
  equipment/water/food/milk sense (700+ passages), so bare "sterilization" is NOT matched:
  only unambiguous coercion/eugenics phrasing counts. Recall is therefore best-effort; see
  the per-topic notes.

Tune the detection by editing TOPIC_SIGNALS (topic key -> regex patterns, matched
case-insensitively against a row's title + snippet). The topic-to-resource mapping and the crisis
numbers live in archive_debugger.crisis, the single source of truth; nothing here holds a number.
"""
from __future__ import annotations

import re
from typing import Optional

from archive_debugger import crisis

TOPIC_SIGNALS: dict[str, list[str]] = {
    # The 1997 Krever inquiry into the contaminated blood system. Kept to the scandal's own
    # vocabulary; routine "blood supply"/"blood-borne" phrasings are intentionally excluded
    # so a blood-donation or infection-control line does not flag.
    "tainted-blood-krever": [
        r"\bkrever\b",
        r"\btainted blood\b",
        r"\bcontaminated blood\b",
        r"\bblood system\b",
    ],
    # Coerced human sterilization / the eugenics era. ONLY unambiguous phrasing: bare
    # "sterilization" is not matched (it is almost always milk/food/water/instrument
    # sterilization in this corpus). A document about coerced sterilization that never uses
    # coercion/eugenics language will be missed; that is the deliberate precision-first bias.
    "coerced-sterilization-indigenous": [
        r"\bsexual steriliz\w*",
        r"\bsterilization act\b",
        r"\b(?:forced|coerced|involuntary|compulsory)\s+steriliz\w*",
        r"\beugenic\w*",
    ],
    "residential-school-health": [
        r"\bresidential school\w*",
        r"\bindian residential\b",
    ],
    # Keyed on "hiv" and the spelled-out forms, which appear in essentially every genuine
    # HIV/AIDS document in this corpus. Bare "aids" is intentionally NOT matched: it collides
    # with hearing/visual/teaching/mobility/band aids in a health corpus. A document naming
    # only "AIDS" with no "HIV" would be missed (rare here).
    "early-hiv-aids": [
        r"\bhiv\b",
        r"\bhiv/aids\b",
        r"\bacquired immune deficiency\b",
        r"\bacquired immunodeficiency\b",
        r"\bhuman immunodeficiency\b",
    ],
}

_COMPILED = {t: [re.compile(p, re.IGNORECASE) for p in pats] for t, pats in TOPIC_SIGNALS.items()}


def _haystack(row: dict) -> str:
    return f"{row.get('title') or ''} {row.get('snippet') or ''}"


def _row_topics(row: dict) -> list[str]:
    hay = _haystack(row)
    return [t for t, pats in _COMPILED.items() if any(p.search(hay) for p in pats)]


def _answer_basis(evidence: list[dict]) -> list[dict]:
    """The rows that are the basis of what the visitor reads: sent to the model (in_prompt)
    or cited. Excludes tangential retrieved-pool rows. Still non-empty on the abstention and
    offline limited-mode paths, where in_prompt marks the top_k shown record."""
    return [r for r in evidence if r.get("in_prompt") or r.get("cited")]


def _crisis_lines(topics: list[str]) -> list[dict]:
    """Resolve the matched topics to their crisis resources from the single source of truth
    (archive_debugger.crisis): ordered by topic, then each topic's display order, de-duplicated."""
    return crisis.resources_for_topics(topics)


def flagged_topics(evidence: list[dict]) -> list[str]:
    """Topic keys whose signal appears in an answer-basis row's title or snippet."""
    found: set[str] = set()
    for row in _answer_basis(evidence):
        found.update(_row_topics(row))
    return sorted(found)


def detect(evidence: list[dict]) -> Optional[dict]:
    """The `flagged` field for the /ask response, or None. `year` is the earliest year among
    the answer-basis rows that matched a topic, for the client's year-aware contextual note.
    `crisis_lines` is the de-duplicated union of the matched topics' mapped lines. The
    visitor-facing note text is rendered client-side from topics + year (not baked here)."""
    topics: set[str] = set()
    years: list[int] = []
    for row in _answer_basis(evidence):
        matched = _row_topics(row)
        if matched:
            topics.update(matched)
            if row.get("year") is not None:
                years.append(int(row["year"]))
    if not topics:
        return None
    ordered = sorted(topics)
    return {"topics": ordered, "year": min(years) if years else None, "crisis_lines": _crisis_lines(ordered)}
