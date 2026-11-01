"""Candidate pages and page pairs for the starter deck, mined deterministically from a collection's
corpus with a fixed seed. A candidate is only a place to look: it becomes a round only after it is
drafted, passes the builder's checks, is judged by the panel and is read by the reviewer.

When Was This? wants one dated body page whose catalogue date is confirmed by the year written on
the page or the item's front matter. Same or Not? wants two pages that share a measure or program
phrase: the same issuer years apart, or different jurisdictions or issuers close in time."""
from __future__ import annotations

import random
import sqlite3
from typing import Optional

from archive_debugger.exhibit import care as care_mod
from archive_debugger.exhibit import pages as pages_mod
from archive_debugger.exhibit.settings import CareRules


def busy_with_dates_or_numbers(text: str, max_years: int, max_digit_share: float) -> bool:
    """A page whose every useful line carries a date, or that is mostly a table of figures, makes no
    fair When Was This? card (the drafting model said so for three cards in four of round 1)."""
    years = len(pages_mod.YEAR.findall(text or ""))
    chars = [c for c in (text or "") if not c.isspace()]
    digits = sum(c.isdigit() for c in chars)
    return years > max_years or (bool(chars) and digits / len(chars) > max_digit_share)


def _date_agrees(conn: sqlite3.Connection, item_id: str, leaf: int, year) -> bool:
    return year is not None and pages_mod.read_date(conn, item_id, leaf, year)["year"] == year


def _body_page(conn: sqlite3.Connection, item_id: str, min_chars: int, max_chars: int, min_leaf: int) -> Optional[int]:
    """The middle body page of an item whose length fits, or None."""
    rows = conn.execute("SELECT leaf_index FROM pages WHERE item_id = ? AND char_count BETWEEN ? AND ? "
                        "AND leaf_index >= ? AND (section_class = 'body' OR section_class IS NULL) "
                        "ORDER BY leaf_index", (item_id, min_chars, max_chars, min_leaf)).fetchall()
    if not rows:
        return None
    return int(rows[len(rows) // 2]["leaf_index"])


def when_candidates(conn: sqlite3.Connection, collection: str, rules: CareRules, cfg: dict, *,
                    seed: int, exclude_items: set = frozenset()) -> list:
    """[{collection, item_id, leaf, year, jurisdiction, date}] spread over decades and jurisdictions."""
    rng = random.Random(f"{seed}:when:{collection}")
    out = []
    for decade in cfg["decades"]:
        rows = conn.execute("SELECT item_id, year, jurisdiction_norm, title FROM items WHERE dated = 1 AND "
                            "date_method = 'exact' AND year BETWEEN ? AND ? ORDER BY item_id",
                            (decade, decade + 9)).fetchall()
        by_jurisdiction: dict = {}
        for r in rows:
            if r["item_id"] in exclude_items:
                continue
            by_jurisdiction.setdefault(r["jurisdiction_norm"] or "unknown", []).append(r)
        for group in by_jurisdiction.values():
            rng.shuffle(group)
        picked = 0
        attempts = 0
        names = sorted(by_jurisdiction)
        while picked < cfg["per_decade"] and attempts < cfg["per_decade"] * 12 and names:
            name = names[attempts % len(names)]
            attempts += 1
            group = by_jurisdiction[name]
            if not group:
                continue
            r = group.pop()
            if care_mod.care_flags([r["title"] or ""], rules):
                continue
            leaf = _body_page(conn, r["item_id"], cfg["min_page_chars"], cfg["max_page_chars"], cfg["min_leaf"])
            if leaf is None:
                continue
            page = pages_mod.page_text(conn, r["item_id"], leaf)
            if page is None or care_mod.care_flags([page.text], rules):
                continue
            if busy_with_dates_or_numbers(page.text, cfg.get("max_years_on_page", 99), cfg.get("max_digit_share", 1.0)):
                continue
            date = pages_mod.read_date(conn, r["item_id"], leaf, r["year"])
            if date["year"] != r["year"]:
                continue
            out.append({"collection": collection, "item_id": r["item_id"], "leaf": leaf, "year": int(r["year"]),
                        "jurisdiction": r["jurisdiction_norm"], "date": date})
            picked += 1
    return out


def _phrase_hits(conn: sqlite3.Connection, phrase: str, limit: int) -> list:
    """Passages that contain the phrase, on dated items, one per item (the first by rank)."""
    query = '"' + phrase.replace('"', " ") + '"'
    rows = conn.execute(
        "SELECT p.passage_id, p.item_id, p.leaf_index, i.year, i.jurisdiction_norm, i.issuer_norm, i.title "
        "FROM passages_fts f JOIN passages p ON p.rowid = f.rowid JOIN items i ON i.item_id = p.item_id "
        "WHERE passages_fts MATCH ? AND i.dated = 1 AND i.date_method = 'exact' ORDER BY f.rank LIMIT ?",
        (query, limit * 4)).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["item_id"] in seen:
            continue
        seen.add(r["item_id"])
        out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def pair_candidates(conn: sqlite3.Connection, collection: str, rules: CareRules, cfg: dict, *, seed: int) -> list:
    """[{collection, phrase, kind ("change" or "compare"), a: {item_id, leaf, year, ...}, b: {...}}]."""
    rng = random.Random(f"{seed}:pairs:{collection}")
    out = []
    used_items: set = set()
    for phrase in cfg["phrases"]:
        hits = [h for h in _phrase_hits(conn, phrase, cfg["hits_per_phrase"]) if h["item_id"] not in used_items]
        rng.shuffle(hits)
        pairs = []
        for i, a in enumerate(hits):
            for b in hits[i + 1:]:
                if a["item_id"] == b["item_id"]:
                    continue
                gap = abs(int(a["year"]) - int(b["year"]))
                same_issuer = a["issuer_norm"] and a["issuer_norm"] == b["issuer_norm"]
                if same_issuer and gap >= cfg["change_min_years"]:
                    pairs.append(("change", a, b))
                elif "compare" in cfg.get("kinds", ("change", "compare")) and not same_issuer and gap <= cfg["compare_max_years"] and \
                        (a["jurisdiction_norm"] != b["jurisdiction_norm"] or a["issuer_norm"] != b["issuer_norm"]):
                    pairs.append(("compare", a, b))
        # Change pairs (the same issuer years apart) are rarer than comparison pairs; take them first.
        pairs.sort(key=lambda p: p[0] != "change")
        kept = 0
        for kind, a, b in pairs:
            if kept >= cfg["pairs_per_phrase"]:
                break
            if a["item_id"] in used_items or b["item_id"] in used_items:
                continue
            if not all(_date_agrees(conn, h["item_id"], h["leaf_index"], h["year"]) for h in (a, b)):
                continue
            texts = []
            for h in (a, b):
                page = pages_mod.page_text(conn, h["item_id"], h["leaf_index"])
                texts += [h["title"] or "", page.text if page else ""]
            if care_mod.care_flags(texts, rules):
                continue
            first, second = sorted((a, b), key=lambda h: (int(h["year"]), h["item_id"]))
            out.append({"collection": collection, "phrase": phrase, "kind": kind,
                        "a": {"item_id": first["item_id"], "leaf": int(first["leaf_index"]), "year": int(first["year"]),
                              "passage_id": first["passage_id"]},
                        "b": {"item_id": second["item_id"], "leaf": int(second["leaf_index"]), "year": int(second["year"]),
                              "passage_id": second["passage_id"]}})
            used_items.update((a["item_id"], b["item_id"]))
            kept += 1
    return out
