"""Care rules for game rounds: stricter than the reading room's notes. The site warns and links help
on a care topic; the exhibit never builds a round on one. A round is refused when any of its text
(page text, quotes, claims, question, explanation) matches an excluded care tier from
archive_debugger.flags, Indigenous context while that is excluded, an excluded term, or a period
term that is now offensive."""
from __future__ import annotations

import re
from typing import Iterable

from archive_debugger import flags
from archive_debugger.exhibit.settings import CareRules


def _term_pattern(term: str) -> re.Pattern:
    words = [re.escape(w) for w in term.lower().split()]
    return re.compile(r"(?<![\w])" + r"[\s-]+".join(words) + r"(?![\w])", re.IGNORECASE)


def care_flags(texts: Iterable[str], rules: CareRules) -> list[str]:
    """Every reason the texts cannot be a game round, sorted; empty when none applies.
    Reasons: "tier-<A|B|C>:<topic>", "indigenous-context", "term:<term>", "period-term:<term>"."""
    hay = flags._norm(" ".join(t for t in texts if t))
    reasons = set()
    for topic in flags._text_topics(hay):
        tier = flags.TIERS.get(topic)
        if tier in rules.excluded_tiers:
            reasons.add(f"tier-{tier}:{topic}")
    if rules.exclude_indigenous_context and any(p.search(hay) for p in flags._INDIGENOUS_CONTEXT):
        reasons.add("indigenous-context")
    for term in rules.excluded_terms:
        if _term_pattern(flags._norm(term)).search(hay):
            reasons.add(f"term:{term}")
    for term in rules.period_terms:
        if _term_pattern(flags._norm(term)).search(hay):
            reasons.add(f"period-term:{term}")
    return sorted(reasons)
