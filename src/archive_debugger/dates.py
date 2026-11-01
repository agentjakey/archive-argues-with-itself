"""Dates read from a document's own pages, kept apart from the catalogue date (docs/formats/derived_dates.md).

The catalogue date, the date read from the document and the capture date are separate fields; a
derived date never overwrites the catalogue date. This module reads only the document's title and its
first pages, by fixed rules written before any accuracy was measured, in this order of trust:

  copyright   a year next to a copyright mark or word ("(c) 1987", "copyright 1987", "droit d'auteur")  high
  imprint     a year in an imprint line ("printed in Canada 1988", "published 1988", "publie en 1988",
              "catalogue no. ... 1988", "ISBN")                                                         high
  fiscal      a fiscal year ("1986-87", "1986-1987", "year ended March 31, 1987"): its closing year      medium
  dated_line  a month and year ("March 1985", "mars 1985")                                              medium
  title       a year in the title                                                                       medium
  year_mode   the most frequent plausible year on the first pages (ties: the latest)                    low

Within one rule the latest year wins (a report cites earlier years; it is published after them). A
year is plausible from 1850 to 2025. Nothing is inferred from outside the document."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Optional

METHOD_VERSION = "dates-1"
FIRST_LEAVES = 6
YEAR_MIN, YEAR_MAX = 1850, 2025
CONFIDENCE = {"copyright": "high", "imprint": "high", "fiscal": "medium", "dated_line": "medium",
              "title": "medium", "year_mode": "low"}

_Y = r"(1[89]\d\d|20[0-2]\d)"
MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
          "janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre")
RULES = (
    ("copyright", re.compile(r"(?:\(c\)|copyright|droit d.auteur)[^0-9]{0,40}" + _Y, re.I)),
    ("imprint", re.compile(r"(?:printed in canada|imprim\w* au canada|published|publi\w+|cat(?:alogue|\.)\s*no\.?|isbn)"
                           r"[^\n]{0,60}?" + _Y, re.I)),
    ("fiscal", re.compile(r"\b" + _Y + r"\s*[-/]\s*(\d{2}|\d{4})\b|year ended[^\n]{0,30}?" + _Y, re.I)),
    ("dated_line", re.compile(r"\b(?:" + MONTHS + r")\s+(?:\d{1,2},?\s+)?" + _Y, re.I)),
)
_BARE = re.compile(r"\b" + _Y + r"\b")


@dataclass
class DerivedDate:
    year: int
    method: str
    confidence: str
    evidence: str
    leaf: Optional[int]
    method_version: str = METHOD_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _plausible(y: int) -> bool:
    return YEAR_MIN <= y <= YEAR_MAX


def _fiscal_year(m: re.Match) -> Optional[int]:
    if m.group(3):
        return int(m.group(3))
    start, end = int(m.group(1)), m.group(2)
    if len(end) == 2:
        close = (start // 100) * 100 + int(end)
        if close < start:
            close += 100
    else:
        close = int(end)
    return close if 0 < close - start <= 1 else None


def _snippet(text: str, m: re.Match) -> str:
    a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
    return " ".join(text[a:b].split())[:120]


def fold(text: str) -> str:
    """Text folded to ASCII for matching: accents dropped, the copyright sign read as (c)."""
    import unicodedata
    text = (text or "").replace(chr(169), "(c)")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def read_date(title: str, pages: list) -> Optional[DerivedDate]:
    """pages: [(leaf_index, text)] of the first pages, in leaf order. Returns the derived date or None."""
    pages = [(leaf, fold(text)) for leaf, text in sorted(pages, key=lambda p: p[0])[:FIRST_LEAVES]]
    title = fold(title)
    for method, rx in RULES:
        found = []
        for leaf, text in pages:
            for m in rx.finditer(text or ""):
                y = _fiscal_year(m) if method == "fiscal" else int([g for g in m.groups() if g][-1])
                if y is not None and _plausible(y):
                    found.append((y, leaf, _snippet(text, m)))
        if found:
            y, leaf, ev = max(found, key=lambda f: (f[0], -f[1]))
            return DerivedDate(y, method, CONFIDENCE[method], ev, leaf)
    title_years = [int(y) for y in _BARE.findall(title or "") if _plausible(int(y))]
    if title_years:
        return DerivedDate(max(title_years), "title", CONFIDENCE["title"], (title or "")[:120], None)
    counts = Counter()
    first_leaf = {}
    for leaf, text in pages:
        for y in _BARE.findall(text or ""):
            y = int(y)
            if _plausible(y):
                counts[y] += 1
                first_leaf.setdefault(y, leaf)
    if counts:
        top = max(counts.values())
        y = max(k for k, v in counts.items() if v == top)
        return DerivedDate(y, "year_mode", CONFIDENCE["year_mode"], f"{y} appears {top} times on the first pages",
                           first_leaf[y])
    return None


def first_pages(conn, item_id: str, leaves: int = FIRST_LEAVES) -> list:
    rows = conn.execute("SELECT leaf_index, text FROM passages WHERE item_id = ? AND leaf_index < ? "
                        "ORDER BY leaf_index, char_start", (item_id, leaves)).fetchall()
    by_leaf: dict = {}
    for leaf, text in rows:
        by_leaf.setdefault(leaf, []).append(text or "")
    return [(leaf, " ".join(texts)) for leaf, texts in sorted(by_leaf.items())]
