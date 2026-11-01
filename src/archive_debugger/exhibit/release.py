"""The exhibit inside a site release (scripts/v2/build_release.py): where its files go, and the gate
that reads them as they will be published.

  exhibit/index.html, exhibit/assets/*   the static app (built with base /exhibit/)
  exhibit/decks/<deck_id>-<sha12>.json    the deck, named by its content, cached for a year
  exhibit/current-deck.json               the pointer the app reads first (never cached): moving it
                                          is how a new deck goes live; the release keeps rollback

The gate refuses an exhibit whose pointer and deck disagree, whose deck is not in the format, or any
round that cannot be traced to a checked page from the release's own text: a page reference that is
not item#leaf, a page link that is not that page's archive.org link, an image from anywhere but
archive.org, a quote that is not in the page text the round shows, a date that is not verified, a
scored year that is not the page's verified year, a round the builder did not pass, a status that is
not publishable, or a round that touches an excluded care topic. While offline image caching is off,
the exhibit may carry no page images at all."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from archive_debugger.exhibit import care as care_mod
from archive_debugger.exhibit import deck as deck_mod
from archive_debugger.exhibit import pages as pages_mod
from archive_debugger.exhibit.settings import Settings

POINTER = "current-deck.json"
DEEP_LINK = re.compile(r"^https://archive\.org/details/([^/]+)/page/n(\d+)$")
IMAGE = re.compile(r"^https://archive\.org/download/([^/]+)/page/n(\d+)_(medium|thumb)\.jpg$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".jp2"}
APP_IMAGES = {"favicon.svg"}


def deck_file_name(deck: dict, raw: bytes) -> str:
    return f"{deck['deck_id']}-{hashlib.sha256(raw).hexdigest()[:12]}.json"


def assemble_exhibit(app: Path, deck_path: Path, out: Path) -> dict:
    """Copy the built app and the deck into out/exhibit; return the pointer written."""
    if not (app / "index.html").exists():
        raise SystemExit(f"{app} has no index.html: build the exhibit app first (cd exhibit/app && npm run build)")
    raw = deck_path.read_bytes()
    deck = json.loads(raw.decode("utf-8"))
    target = out / "exhibit"
    shutil.copytree(app, target, dirs_exist_ok=True)
    name = deck_file_name(deck, raw)
    (target / "decks").mkdir(parents=True, exist_ok=True)
    (target / "decks" / name).write_bytes(raw)
    pointer = {"deck": name, "deck_id": deck["deck_id"], "sha256": hashlib.sha256(raw).hexdigest()}
    (target / POINTER).write_text(json.dumps(pointer, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return pointer


def round_problems(rnd: dict, s: Settings) -> list:
    rid = rnd.get("id", "?")
    out = []
    if rnd.get("status") not in deck_mod.PUBLISHABLE:
        out.append(f"{rid}: status {rnd.get('status')} is not publishable")
    checks = rnd.get("checks") or {}
    if not checks.get("builder_version") or checks.get("refusals"):
        out.append(f"{rid}: the builder did not pass this round")
    pages = {}
    for p in rnd.get("pages") or []:
        try:
            item_id, leaf = pages_mod.parse_page_ref(p.get("ref", ""))
        except ValueError:
            out.append(f"{rid}: page reference {p.get('ref')!r} is not item#leaf")
            continue
        link = DEEP_LINK.match(p.get("details_url") or "")
        if not link or link.group(1) != item_id or int(link.group(2)) != leaf:
            out.append(f"{rid}: {p['ref']} has no link to its own page on archive.org")
        for key in ("image_url", "thumb_url"):
            img = IMAGE.match(p.get(key) or "")
            if not img or img.group(1) != item_id or int(img.group(2)) != leaf:
                out.append(f"{rid}: {p['ref']} {key} is not that page on archive.org's image service")
        if not (p.get("text") or "").strip() or not p.get("text_sha256"):
            out.append(f"{rid}: {p['ref']} has no page text")
        cat, read = p.get("catalogue_date") or {}, p.get("page_date") or {}
        if not (p.get("date_verified") and cat.get("year") is not None and read.get("year") == cat.get("year")
                and read.get("line") and str(cat.get("year")) in read.get("line", "")):
            out.append(f"{rid}: {p['ref']} date is not verified")
        pages[p.get("ref")] = p.get("text") or ""
    for q in rnd.get("quotes") or []:
        if q.get("page_ref") not in pages:
            out.append(f"{rid}: quote {q.get('id')} names a page the round does not carry")
        elif not pages_mod.on_page(q.get("text") or "", pages[q["page_ref"]]):
            out.append(f"{rid}: quote {q.get('id')} is not in the page text the round shows")
    if rnd.get("mode") == "when_was_this":
        first = (rnd.get("pages") or [{}])[0]
        if (rnd.get("play") or {}).get("year") != (first.get("catalogue_date") or {}).get("year"):
            out.append(f"{rid}: the scored year is not the page's verified year")
    if rnd.get("mode") == "same_or_not" and (rnd.get("play") or {}).get("answer") not in deck_mod.SAME_OR_NOT_CHOICES:
        out.append(f"{rid}: no valid answer")
    flags = care_mod.care_flags(deck_mod.round_texts(rnd), s.care)
    if flags:
        out.append(f"{rid}: touches excluded care topics {flags}")
    if rnd.get("explanation_status") not in deck_mod.EXPLANATION_STATES:
        out.append(f"{rid}: explanation status {rnd.get('explanation_status')!r} is not one the deck format names")
    return out


def exhibit_problems(release: Path, s: Settings) -> list:
    """Every problem with the exhibit in this release; empty when it may ship (or when the release
    carries no exhibit)."""
    root = release / "exhibit"
    if not root.exists():
        return []
    problems = []
    if not (root / "index.html").exists():
        problems.append("exhibit/index.html is missing")
    pointer_path = root / POINTER
    if not pointer_path.exists():
        return problems + [f"exhibit/{POINTER} is missing"]
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    deck_path = root / "decks" / str(pointer.get("deck", ""))
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.json", str(pointer.get("deck", ""))) or not deck_path.exists():
        return problems + [f"exhibit/{POINTER} names a deck that is not in exhibit/decks/"]
    raw = deck_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer.get("sha256"):
        problems.append("exhibit: the deck's sha256 is not the pointer's")
    deck = json.loads(raw.decode("utf-8"))
    if deck.get("format") != deck_mod.FORMAT:
        return problems + [f"exhibit: deck format {deck.get('format')!r} is not {deck_mod.FORMAT}"]
    if (deck.get("settings") or {}).get("panel_calibrated") is not False:
        # No calibration of the panel covers exhibit rounds yet (Gate 2 calibrates citation checks on
        # answers), so the deck must say its AI judgments are uncalibrated.
        problems.append("exhibit: the deck does not say the panel is uncalibrated")
    for rnd in deck.get("rounds") or []:
        problems += round_problems(rnd, s)
    if not s.offline_image_cache:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES and path.name not in APP_IMAGES:
                problems.append(f"exhibit: {path.relative_to(release).as_posix()} is a page image, but offline caching is off")
    return problems
