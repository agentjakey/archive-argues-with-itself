"""Pages from a collection's corpus database (opened read-only), as a deck stores them.

A page is one leaf of one item: its text is the item's passages on that leaf in order. Its dates are
kept apart: the catalogue date (the item's catalogue record, with how it was normalized) and a date
read from the document (a year written on this page or on the item's front matter, with the line it
was read from). A date is verified when the two agree to the year and the line is on the page it
names. A derived date never overwrites the catalogue date."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from archive_debugger.audit import collections as collections_mod
from archive_debugger.audit.gates import fold
from archive_debugger.retrieve import citation

FRONT_MATTER_LEAVES = 6          # leaves 0..5: cover, title page and the verso that carries the date
DATE_CONTEXT_CHARS = 70           # characters kept on each side of a year read from a page
YEAR = re.compile(r"(?<![0-9])(1[89][0-9]{2}|20[0-2][0-9])(?![0-9])")


def open_collection(name: str) -> tuple:
    """(collection config, read-only connection) for a collection named in config/collections."""
    from archive_debugger.audit.run import corpus_connection
    coll = collections_mod.load(name)
    return coll, corpus_connection(coll)


def page_ref(item_id: str, leaf: int) -> str:
    return f"{item_id}#{int(leaf)}"


def parse_page_ref(ref: str) -> tuple:
    item_id, _, leaf = ref.rpartition("#")
    if not item_id or not leaf.isdigit():
        raise ValueError(f"not a page reference (item#leaf): {ref!r}")
    return item_id, int(leaf)


def text_fingerprint(text: str) -> str:
    """sha256 of the page text folded to ASCII words, so a copy that lost accents or line breaks
    still matches; the deck stores it and the release gate compares it."""
    return hashlib.sha256(fold(text).encode("utf-8")).hexdigest()


def on_page(quote: str, text: str) -> bool:
    """A quote is on a page when its words, folded to ASCII, appear in order in the page's words."""
    q = fold(quote)
    return bool(q) and f" {q} " in f" {fold(text)} "


@dataclass(frozen=True)
class PageText:
    item_id: str
    leaf: int
    text: str
    passage_ids: tuple


def page_text(conn: sqlite3.Connection, item_id: str, leaf: int) -> Optional[PageText]:
    rows = conn.execute("SELECT passage_id, text FROM passages WHERE item_id = ? AND leaf_index = ? "
                        "ORDER BY char_start, passage_id", (item_id, int(leaf))).fetchall()
    if not rows:
        return None
    return PageText(item_id, int(leaf), "\n".join(r["text"] or "" for r in rows), tuple(r["passage_id"] for r in rows))


def item_meta(conn: sqlite3.Connection, item_id: str) -> Optional[dict]:
    row = conn.execute("SELECT item_id, title, issuer_norm, publisher_raw, creator_raw, jurisdiction_norm, "
                       "date_raw, date_method, year, dated, language, page_count FROM items WHERE item_id = ?",
                       (item_id,)).fetchone()
    return dict(row) if row else None


def year_line(text: str, year: int) -> Optional[str]:
    """The stretch of page text around the first place `year` is written, cut at word edges, or
    None when the page does not carry it."""
    for match in YEAR.finditer(text or ""):
        if int(match.group(1)) != int(year):
            continue
        start = max(0, match.start() - DATE_CONTEXT_CHARS)
        end = min(len(text), match.end() + DATE_CONTEXT_CHARS)
        while start > 0 and not text[start - 1].isspace():
            start += 1
        while end < len(text) and not text[end].isspace():
            end -= 1
        return " ".join(text[start:end].split())
    return None


def read_date(conn: sqlite3.Connection, item_id: str, leaf: int, year: Optional[int]) -> dict:
    """Look for the catalogue year written on this page, then on the item's front matter.
    Returns {"year", "method", "page_ref", "line"}: method "read_from_page", "read_from_front_matter"
    or "not_found"."""
    if year is None:
        return {"year": None, "method": "not_found", "page_ref": None, "line": None}
    candidates = [int(leaf)] + [n for n in range(FRONT_MATTER_LEAVES) if n != int(leaf)]
    for n in candidates:
        page = page_text(conn, item_id, n)
        if page is None:
            continue
        line = year_line(page.text, year)
        if line:
            method = "read_from_page" if n == int(leaf) else "read_from_front_matter"
            return {"year": int(year), "method": method, "page_ref": page_ref(item_id, n), "line": line}
    return {"year": None, "method": "not_found", "page_ref": None, "line": None}


def cut_text(text: str, keep: list, max_chars: int) -> tuple:
    """The page text, cut to about max_chars around the kept quotes when it is longer. Cuts fall on
    line breaks. Returns (text, cut)."""
    if len(text) <= max_chars:
        return text, False
    folded_lines = text.split("\n")
    spans = []
    offset = 0
    for line in folded_lines:
        spans.append((offset, offset + len(line)))
        offset += len(line) + 1
    anchor = 0
    for q in keep:
        words = re.findall(r"[^\W_]+", q)[:4]
        if not words:
            continue
        found = re.search(r"[\W_]+".join(re.escape(w) for w in words), text, re.IGNORECASE)
        if found:
            anchor = found.start()
            break
    start = max(0, anchor - max_chars // 3)
    end = min(len(text), start + max_chars)
    start = max(0, end - max_chars)
    for a, b in spans:
        if a <= start <= b:
            start = a
            break
    for a, b in spans:
        if a <= end <= b:
            end = b
            break
    return text[start:end], True


def page_record(conn: sqlite3.Connection, collection: str, item_id: str, leaf: int, *, keep_quotes: list,
                max_chars: int) -> Optional[dict]:
    """The deck's record of one page, or None when the page does not resolve."""
    meta = item_meta(conn, item_id)
    page = page_text(conn, item_id, leaf)
    if meta is None or page is None:
        return None
    catalogue_year = meta["year"] if meta["dated"] else None
    read = read_date(conn, item_id, leaf, catalogue_year)
    shown, cut = cut_text(page.text, keep_quotes, max_chars)
    verified = (catalogue_year is not None and meta["date_method"] == "exact" and read["year"] == catalogue_year)
    return {
        "ref": page_ref(item_id, leaf),
        "collection": collection,
        "item_id": item_id,
        "leaf": int(leaf),
        "title": meta["title"],
        "issuer": meta["issuer_norm"] or meta["publisher_raw"] or meta["creator_raw"],
        "jurisdiction": meta["jurisdiction_norm"],
        "language": meta["language"],
        "catalogue_date": {"year": catalogue_year, "raw": meta["date_raw"], "method": meta["date_method"]},
        "page_date": read,
        "date_verified": verified,
        "date_verification": "catalogue_and_page_agree" if verified else "unverified",
        "text": shown,
        "text_cut": cut,
        "text_sha256": text_fingerprint(page.text),
        "passage_ids": list(page.passage_ids),
        "details_url": citation.deep_link(item_id, leaf),
        "image_url": citation.page_image(item_id, leaf),
        "thumb_url": citation.page_thumb(item_id, leaf),
    }
