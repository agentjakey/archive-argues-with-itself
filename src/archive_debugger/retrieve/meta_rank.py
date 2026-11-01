"""Year, place and issuer as ranking features (Phase 3).

The filters (retrieve/filters.py) remove what a reader excluded. This module reorders what is left
using what the question itself names: a year or range ("in 1985", "between 1974 and 1999", "the
1980s"), an "as of" year ("as of 1990", "by 1990"), a province or territory, or an issuer whose
distinctive words all appear in the question. A request's own year filters count as well, and an as
of year (from the question or the as_of_year filter) prefers the most recent records up to it.

Everything here is deterministic and reads only the question, the filters and the catalogue fields
already on each hit (year, jurisdiction, issuer). With every weight zero, which is the default, the
ranking is returned untouched (the same list object). The weights live in the collection config:

    [rank]
    year = 0.0        # hit's catalogue year inside the year or range the question names
    place = 0.0       # hit's jurisdiction is one the question names
    issuer = 0.0      # hit's issuer is one the question names
    recency = 0.0     # with an as of year: up to this much for the latest year at or before it

A hit's new score is score * (1 + the sum of the bonuses that apply). Weights join the answer cache
context (digest()), so changing them never serves an answer ranked the old way."""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

WEIGHT_NAMES = ("year", "place", "issuer", "recency")
YEAR_MIN, YEAR_MAX = 1800, 2100
RECENCY_SPAN = 20   # years before the as of year over which the recency bonus falls to zero

# Province and territory names as readers write them (English and French, accents folded), to the
# catalogue's jurisdiction_norm values. "Canada" and "federal" are not here: almost every question
# is about Canada, so the word says nothing about which government.
PLACES = {
    "ontario": "ontario",
    "quebec": "quebec",
    "british columbia": "british_columbia", "colombie britannique": "british_columbia",
    "alberta": "alberta",
    "manitoba": "manitoba",
    "saskatchewan": "saskatchewan",
    "nova scotia": "nova_scotia", "nouvelle ecosse": "nova_scotia",
    "new brunswick": "new_brunswick", "nouveau brunswick": "new_brunswick",
    "newfoundland": "newfoundland", "labrador": "newfoundland", "terre neuve": "newfoundland",
    "prince edward island": "prince_edward_island", "ile du prince edouard": "prince_edward_island",
    "yukon": "yukon",
    "northwest territories": "northwest_territories", "territoires du nord ouest": "northwest_territories",
    "nunavut": "nunavut",
}

# Words too common in issuer names to identify one ("Ontario Ministry of Health": only "ontario" is
# distinctive, and a province already counts as a place).
ISSUER_STOP = {
    "of", "the", "and", "for", "on", "in", "de", "du", "des", "la", "le", "et", "canada", "canadian",
    "government", "ministry", "minister", "department", "dept", "office", "board", "council",
    "commission", "committee", "agency", "branch", "division", "services", "service", "health",
    "provincial", "federal", "portfolio", "unknown", "royal", "into", "inc", "ltd",
} | {w for name in PLACES for w in name.split()}

_YEAR = r"(1[89][0-9]{2}|20[0-9]{2}|2100)"
_RANGE = re.compile(r"\b(?:between|from)\s+" + _YEAR + r"\s+(?:and|to|until|through)\s+" + _YEAR + r"\b")
# fold() turns "1974-1999" into "1974 1999", so a span is two years side by side or joined by "to".
_SPAN = re.compile(r"\b" + _YEAR + r"\s+(?:to\s+)?" + _YEAR + r"\b")
_AS_OF = re.compile(r"\b(?:as of|by|up to|until|before)\s+" + _YEAR + r"\b")
_DECADE = re.compile(r"\b(1[89][0-9]0|20[0-9]0)s\b")
_LONE_YEAR = re.compile(r"\b" + _YEAR + r"\b")


def fold(text: str) -> str:
    """Lowercase, accents removed, anything not a letter or digit as one space."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass
class Constraints:
    years: list = field(default_factory=list)       # [(lo, hi)] inclusive ranges the question names
    as_of: Optional[int] = None
    places: set = field(default_factory=set)        # jurisdiction_norm values
    words: frozenset = frozenset()                  # the question's folded words, for issuer matching

    def to_dict(self) -> dict:
        return {"years": [list(r) for r in self.years], "as_of": self.as_of, "places": sorted(self.places)}


def question_constraints(question: str) -> Constraints:
    text = fold(question)
    out = Constraints(words=frozenset(text.split()))
    taken = []

    def free(match) -> bool:
        return not any(s <= match.start() < e for s, e in taken)

    for pattern in (_RANGE, _SPAN):
        for m in pattern.finditer(text):
            if free(m):
                lo, hi = sorted((int(m.group(1)), int(m.group(2))))
                out.years.append((lo, hi))
                taken.append(m.span())
    for m in _AS_OF.finditer(text):
        if free(m):
            out.as_of = int(m.group(1)) if out.as_of is None else min(out.as_of, int(m.group(1)))
            taken.append(m.span())
    for m in _DECADE.finditer(text):
        if free(m):
            start = int(m.group(1))
            out.years.append((start, start + 9))
            taken.append(m.span())
    for m in _LONE_YEAR.finditer(text):
        if free(m):
            year = int(m.group(1))
            out.years.append((year, year))
    padded = f" {text} "
    for name, value in PLACES.items():
        if f" {name} " in padded:
            out.places.add(value)
    return out


def issuer_words(issuer: Optional[str]) -> frozenset:
    """The distinctive words of an issuer name; empty when it has none."""
    return frozenset(w for w in fold(issuer or "").split() if w not in ISSUER_STOP and len(w) > 2)


def load_weights(config_path: Path) -> dict:
    """The [rank] weights of a collection config; every missing weight is 0.0."""
    with Path(config_path).open("rb") as fh:
        section = tomllib.load(fh).get("rank", {}) or {}
    unknown = set(section) - set(WEIGHT_NAMES)
    if unknown:
        raise ValueError(f"unknown [rank] keys: {sorted(unknown)}")
    return {name: float(section.get(name, 0.0) or 0.0) for name in WEIGHT_NAMES}


def active(weights: Optional[dict]) -> bool:
    return bool(weights) and any(float(weights.get(n, 0.0) or 0.0) != 0.0 for n in WEIGHT_NAMES)


def digest(weights: Optional[dict]) -> str:
    """A short hash of the weights for the cache context; "" when ranking is untouched."""
    if not active(weights):
        return ""
    canonical = json.dumps({n: float(weights.get(n, 0.0) or 0.0) for n in WEIGHT_NAMES}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def bonuses(hit: dict, c: Constraints, weights: dict) -> dict:
    """The bonus each feature gives one hit (only features that apply)."""
    out = {}
    year = hit.get("year")
    if weights.get("year") and c.years and isinstance(year, int):
        if any(lo <= year <= hi for lo, hi in c.years):
            out["year"] = weights["year"]
    if weights.get("place") and c.places and hit.get("jurisdiction") in c.places:
        out["place"] = weights["place"]
    if weights.get("issuer"):
        words = issuer_words(hit.get("issuer"))
        if words and words <= c.words:
            out["issuer"] = weights["issuer"]
    if weights.get("recency") and c.as_of is not None and isinstance(year, int) and year <= c.as_of:
        out["recency"] = weights["recency"] * max(0.0, 1.0 - (c.as_of - year) / RECENCY_SPAN)
    return out


def rerank(hits: list, question: str, weights: Optional[dict], filters=None) -> list:
    """The hits reordered by score * (1 + bonuses); the same list when no weight is set. Ties keep the
    original order. Each moved hit records its bonuses under "rank_features"."""
    if not active(weights) or not hits:
        return hits
    c = question_constraints(question)
    if filters is not None:
        lo, hi = getattr(filters, "year_from", None), getattr(filters, "year_to", None)
        if lo is not None or hi is not None:
            c.years.append((int(lo) if lo is not None else YEAR_MIN, int(hi) if hi is not None else YEAR_MAX))
        as_of = getattr(filters, "as_of_year", None)
        if as_of is not None:
            c.as_of = int(as_of) if c.as_of is None else min(c.as_of, int(as_of))
    scored = []
    for position, hit in enumerate(hits):
        b = bonuses(hit, c, weights)
        base = float(hit.get("score") or 0.0)
        new = dict(hit)
        if b:
            new["rank_features"] = {k: round(v, 6) for k, v in b.items()}
        scored.append((-(base * (1.0 + sum(b.values()))), position, new))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored]
