"""The deck format (docs/formats/exhibit-deck.md) and the builder's refusal checks.

check_round reads a round against the collection's corpus database and returns every reason it
cannot be published:

  page_unresolved       a page's item and leaf have no text in the collection
  page_text_changed     the stored page text no longer matches the page (fingerprint)
  quote_not_on_page     a quote is not on the page it names, or not in the text the round shows
  date_unverified       a page's catalogue date and the date read from the document do not agree
  answer_year_unverified (When Was This?) the scored year is not the page's verified date
  care:<reason>         the round touches an excluded care topic (archive_debugger.exhibit.care)
  malformed:<what>      the round is not in the deck format

A refused round is written to the rejected file with its reasons and never reaches a visitor."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Callable, Optional

from archive_debugger.exhibit import care as care_mod
from archive_debugger.exhibit import pages as pages_mod
from archive_debugger.exhibit.settings import CareRules

FORMAT = "exhibit-deck/1"
MODES = ("same_or_not", "when_was_this", "time_dial")
SAME_OR_NOT_CHOICES = ("same_thing_changed", "real_disagreement", "not_comparable", "not_enough_evidence")
QUOTE_ROLES = ("claim", "decisive", "clue", "date", "evidence")
STATUSES = ("draft", "refused", "flagged", "model-reviewed", "author-reviewed", "author-rejected")
# Only these reach a published deck. A model-reviewed round carries its status to the screen.
PUBLISHABLE = ("model-reviewed", "author-reviewed")
EXPLANATION_STATES = ("model-drafted", "author-reviewed", "author-edited")


def _malformed(rnd: dict) -> list:
    out = []
    for key in ("id", "mode", "collection", "pages", "quotes", "play", "status", "explanation", "provenance"):
        if key not in rnd:
            out.append(f"malformed:missing {key}")
    if out:
        return out
    if rnd["mode"] not in MODES:
        out.append(f"malformed:mode {rnd['mode']}")
    if rnd["status"] not in STATUSES:
        out.append(f"malformed:status {rnd['status']}")
    if not rnd["pages"]:
        out.append("malformed:no pages")
    refs = {p.get("ref") for p in rnd["pages"]}
    for q in rnd["quotes"]:
        if q.get("page_ref") not in refs:
            out.append(f"malformed:quote {q.get('id')} names a page the round does not carry")
        if q.get("role") not in QUOTE_ROLES:
            out.append(f"malformed:quote {q.get('id')} role {q.get('role')}")
    quote_ids = {q.get("id") for q in rnd["quotes"]}
    play = rnd["play"]
    if rnd["mode"] == "same_or_not":
        if len(rnd["pages"]) != 2:
            out.append("malformed:same_or_not needs two pages")
        if play.get("answer") not in SAME_OR_NOT_CHOICES:
            out.append(f"malformed:answer {play.get('answer')}")
        if len(play.get("claims") or []) != 2:
            out.append("malformed:same_or_not needs two claims")
        if not set(play.get("decisive") or []) <= quote_ids or not play.get("decisive"):
            out.append("malformed:decisive lines must name the round's quotes")
    elif rnd["mode"] == "when_was_this":
        if len(rnd["pages"]) != 1:
            out.append("malformed:when_was_this needs one page")
        # A missing year is refused below as unverified, not as malformed.
        if play.get("year") is not None and not isinstance(play.get("year"), int):
            out.append("malformed:when_was_this year must be a whole year")
        if not set(play.get("clues") or []) <= quote_ids or not play.get("clues"):
            out.append("malformed:clues must name the round's quotes")
    elif rnd["mode"] == "time_dial":
        epochs = play.get("epochs") or []
        if not epochs:
            out.append("malformed:time_dial needs epochs")
        years = [e.get("year") for e in epochs]
        if years != sorted(years):
            out.append("malformed:epochs out of order")
        for e in epochs:
            if not set(e.get("quotes") or []) <= quote_ids:
                out.append(f"malformed:epoch {e.get('year')} names a quote the round does not carry")
    return out


def round_texts(rnd: dict) -> list:
    """Everything a visitor can read in a round, for the care check."""
    texts = []
    for p in rnd.get("pages") or []:
        texts += [p.get("title") or "", p.get("text") or ""]
    texts += [q.get("text") or "" for q in rnd.get("quotes") or []]
    for lang_map in [rnd.get("explanation") or {}] + [c.get("text") or {} for c in (rnd.get("play") or {}).get("claims") or []]:
        texts += [v for v in lang_map.values() if isinstance(v, str)]
    play = rnd.get("play") or {}
    if isinstance(play.get("question"), dict):
        texts += [v for v in play["question"].values() if isinstance(v, str)]
    for e in play.get("epochs") or []:
        texts += [v for v in (e.get("answer") or {}).values() if isinstance(v, str)]
    return texts


def check_round(rnd: dict, connect: Callable[[str], sqlite3.Connection], rules: CareRules) -> list:
    """Every reason this round must be refused; empty when it may go on to review. `connect` maps a
    collection name to a read-only connection to its corpus."""
    reasons = _malformed(rnd)
    if reasons:
        return reasons
    conn = connect(rnd["collection"])
    by_ref = {}
    for p in rnd["pages"]:
        item_id, leaf = pages_mod.parse_page_ref(p["ref"])
        page = pages_mod.page_text(conn, item_id, leaf)
        if page is None:
            reasons.append(f"page_unresolved:{p['ref']}")
            continue
        by_ref[p["ref"]] = page.text
        if pages_mod.text_fingerprint(page.text) != p.get("text_sha256"):
            reasons.append(f"page_text_changed:{p['ref']}")
        if not p.get("text") or not pages_mod.on_page(p["text"], page.text):
            reasons.append(f"page_text_changed:{p['ref']} (shown text is not the page's)")
        reasons += _date_reasons(conn, p)
    for q in rnd["quotes"]:
        full = by_ref.get(q["page_ref"])
        shown = next((p.get("text") or "" for p in rnd["pages"] if p["ref"] == q["page_ref"]), "")
        if full is None:
            continue
        if q.get("role") == "date":
            # A date line may come from the front matter, which the round does not show.
            continue
        if not pages_mod.on_page(q["text"], full) or not pages_mod.on_page(q["text"], shown):
            reasons.append(f"quote_not_on_page:{q['id']}")
    if rnd["mode"] == "when_was_this":
        page = rnd["pages"][0]
        if not page.get("date_verified") or rnd["play"].get("year") != (page.get("catalogue_date") or {}).get("year"):
            reasons.append("answer_year_unverified")
    reasons += [f"care:{r}" for r in care_mod.care_flags(round_texts(rnd), rules)]
    return sorted(set(reasons))


def _date_reasons(conn: sqlite3.Connection, page: dict) -> list:
    """A page's date is verified when its catalogue year (normalized exactly) equals the year read
    from the document, and the line it was read from is on the page it names."""
    cat = page.get("catalogue_date") or {}
    read = page.get("page_date") or {}
    ok = (page.get("date_verified") and cat.get("method") == "exact" and cat.get("year") is not None
          and read.get("year") == cat.get("year") and read.get("line") and read.get("page_ref"))
    if not ok:
        return [f"date_unverified:{page.get('ref')}"]
    item_id, leaf = pages_mod.parse_page_ref(read["page_ref"])
    if item_id != page["item_id"]:
        return [f"date_unverified:{page.get('ref')} (date read from another item)"]
    source = pages_mod.page_text(conn, item_id, leaf)
    if source is None or not pages_mod.on_page(read["line"], source.text):
        return [f"date_unverified:{page.get('ref')} (date line not on {read['page_ref']})"]
    db_year = conn.execute("SELECT year, date_method, dated FROM items WHERE item_id = ?", (item_id,)).fetchone()
    if db_year is None or not db_year["dated"] or db_year["year"] != cat.get("year") or db_year["date_method"] != "exact":
        return [f"date_unverified:{page.get('ref')} (catalogue date differs from the collection's)"]
    return []


def round_fingerprint(rnd: dict) -> str:
    """A content hash of the round without its review fields, so a review is tied to what was read."""
    body = {k: v for k, v in rnd.items() if k not in ("status", "review", "checks")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


def deck_document(deck_id: str, built_at: str, builder_version: str, rounds: list, gap_hunt: Optional[dict],
                  settings_summary: dict) -> dict:
    return {
        "format": FORMAT,
        "deck_id": deck_id,
        "built_at": built_at,
        "builder_version": builder_version,
        "settings": settings_summary,
        "counts": {m: sum(1 for r in rounds if r["mode"] == m) for m in MODES},
        "rounds": rounds,
        "gap_hunt": gap_hunt,
    }
