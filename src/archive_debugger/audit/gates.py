"""Deterministic gates (docs/formats/audit.md), run on every item before any model sees it.

  VALID, citation check 1: each cited passage exists in the collection's corpus database with the
  same item and leaf, its text in the item is the database text, its page link is the page's own,
  and it was in the answer's retrieved evidence. When the answer's retrieved evidence was not
  recorded, the result is "unrecorded": the page resolves, the retrieval cannot be confirmed.
  Quotes: a span in quotation marks of three words or more must appear on a cited page.
  Years: a year written in the sentence should appear on a cited page or be the page's year;
  one that does not is flagged for the judges and reviewers, never turned into a verdict here.

Passing VALID proves nothing about SUPPORTS, ANSWERS or IN SCOPE. The corpus is opened read-only."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Optional

GATE_VERSION = 1
OPEN_QUOTES = "\"" + chr(0x201C)
CLOSE_QUOTES = "\"" + chr(0x201D)
QUOTE = re.compile("[" + OPEN_QUOTES + "]([^" + OPEN_QUOTES + CLOSE_QUOTES + "]{3,400})[" + CLOSE_QUOTES + "]")
YEAR = re.compile(r"(?<![0-9])(1[89][0-9]{2}|20[0-9]{2})(?![0-9])")
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def squash(text: Optional[str]) -> str:
    """Lowercase words joined by single spaces: punctuation, OCR line breaks and spacing ignored."""
    return " ".join(WORD.findall((text or "").lower()))


def page_link(item: str, leaf: int) -> str:
    return f"https://archive.org/details/{item}/page/n{int(leaf)}"


def fold(text: Optional[str]) -> str:
    """The text as an ASCII copy of it would read: accents removed (e with an accent becomes e)
    and every other non-ASCII character dropped, then squashed."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return squash("".join(ch for ch in decomposed if ord(ch) < 128))


def compare_text(stored: Optional[str], given: Optional[str]) -> str:
    """"exact" when the two texts have the same words; "ascii_folded" when they are the same once
    both are folded to ASCII (an earlier copy of the text dropped accents and symbols); "differs"
    otherwise."""
    if squash(stored) == squash(given):
        return "exact"
    if fold(stored) == fold(given):
        return "ascii_folded"
    return "differs"


def check_citation(conn: sqlite3.Connection, cite: dict, retrieved: Optional[list]) -> dict:
    row = conn.execute("SELECT passage_id, item_id, leaf_index, text FROM passages WHERE passage_id = ?",
                       (cite["passage_id"],)).fetchone()
    exists = row is not None and row["item_id"] == cite["item_id"] and int(row["leaf_index"]) == int(cite["leaf_index"])
    text = compare_text(row["text"], cite.get("text")) if exists else "differs"
    link_ok = cite.get("deep_link") == page_link(cite["item_id"], cite["leaf_index"])
    in_retrieved = None if retrieved is None else cite["passage_id"] in retrieved
    return {"passage_id": cite["passage_id"], "exists": exists, "text": text,
            "text_matches": text in ("exact", "ascii_folded"), "page_link": link_ok, "in_retrieved": in_retrieved}


def valid_verdict(checks: list) -> str:
    if not checks:
        return "fail"
    if not all(c["exists"] and c["text_matches"] and c["page_link"] for c in checks):
        return "fail"
    if any(c["in_retrieved"] is False for c in checks):
        return "fail"
    if any(c["in_retrieved"] is None for c in checks):
        return "unrecorded"
    return "pass"


def quote_checks(sentence: str, pages: list) -> list:
    out = []
    joined = " ".join(squash(p) for p in pages)
    for match in QUOTE.finditer(sentence or ""):
        quoted = squash(match.group(1))
        if len(quoted.split()) < 3:
            continue
        out.append({"text": match.group(1), "on_page": quoted in joined})
    return out


def year_checks(sentence: str, citations: list) -> list:
    out = []
    page_text = " ".join(c.get("text") or "" for c in citations)
    page_years = {c.get("year") for c in citations if c.get("year") is not None}
    for year in dict.fromkeys(YEAR.findall(sentence or "")):
        on_page = re.search(rf"(?<![0-9]){year}(?![0-9])", page_text) is not None
        out.append({"year": int(year), "on_page": on_page, "is_page_year": int(year) in page_years})
    return out


def run_gates(conn: sqlite3.Connection, item: dict) -> dict:
    checks = [check_citation(conn, c, item.get("retrieved_ids")) for c in item["citations"]]
    quotes = quote_checks(item["sentence"], [c.get("text") for c in item["citations"]])
    years = year_checks(item["sentence"], item["citations"])
    flags = []
    if any(not q["on_page"] for q in quotes):
        flags.append("quote_not_on_page")
    if any(not y["on_page"] and not y["is_page_year"] for y in years):
        flags.append("year_not_on_page")
    return {"item_id": item["item_id"], "gate_version": GATE_VERSION, "valid": valid_verdict(checks),
            "citations": checks, "quotes": quotes, "years": years, "flags": flags}
