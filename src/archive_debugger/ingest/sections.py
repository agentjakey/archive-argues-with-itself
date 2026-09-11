"""Deterministic page classifier: section_class in {front, body, back} from leaf
position and text signals (title page, table of contents, letter of transmittal,
index, bibliography / reference-list patterns, page-number-dense lines).

Computed ONCE by this ingest command into pages.section_class / pages.section_method;
never at query time. No labels, no model, no network. Retrieval may down-weight
front/back matter (config, off by default), never exclude it. Pages with no text
stay NULL (they hold no passages, so nothing is retrieved from them anyway).

Scale: pages are walked in item and leaf order, each page's passages are fetched
by the page index, classification happens in memory, and the two columns are
written with executemany in batches (one short transaction per batch). The run
switches the db to WAL with synchronous=NORMAL and restores the prior journal
mode afterwards. Another connection holding the db aborts the run up front.

Thresholds are a priori and recorded here; the report samples 20 pages per class
so precision can be eyeballed before the switch is turned on."""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.ingest import db

FRONT_SHARE, FRONT_MIN = 0.06, 3      # front zone: the first max(3, ceil(6% of leaves)) leaves
BACK_SHARE, BACK_MIN = 0.05, 2        # back zone: the last max(2, ceil(5% of leaves)) leaves
CLASSES = ("front", "body", "back")
BATCH = 10_000

_TOC = re.compile(r"\b(table of )?contents\b|\blist of (tables|figures|appendices|illustrations)\b", re.IGNORECASE)
_TRANSMITTAL = re.compile(
    r"letter of transmittal|i have the honou?r to (present|submit|transmit)|respectfully submitted", re.IGNORECASE)
_INDEX_HEAD = re.compile(r"^\s*(subject |general |alphabetical )?index\s*$", re.IGNORECASE | re.MULTILINE)
_REF_HEAD = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited|sources consulted|selected bibliography)\s*$",
    re.IGNORECASE | re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\(?\d{1,3}[.)]\s+\S", re.MULTILINE)                       # "12. Smith J ..."
# Citation signature (v2). v1 accepted any "year ... digits:digits" and fired on times
# and ratios in statistical tables and minutes (back precision ~60% in the sample).
# v2 needs a year and, within 60 characters, a volume:page-RANGE ("1991;12(4):50-52",
# "1946. ... 28: 262-266", "1994 : 26-31") or an explicit page range ("pp. 12-19").
_CITE = re.compile(
    r"\b(1[89]\d\d|20\d\d)\b[^\n]{0,60}?(?:\b\d{1,4}\s*(?:\(\d+\))?\s*:\s*\d{1,4}\s*-\s*\d{1,4}\b"
    r"|\bpp?\.\s*\d{1,4}\s*-\s*\d{1,4}\b)")
# Author-list evidence: a line, or a sentence after a period/semicolon, opening with a
# Title-case surname and initials closed by a period or comma: "Kaiserman MJ," /
# "Silverman, L.," / "Holmes, H.B.," / "Monk, M. 1991". Title-case only, because
# ALL-CAPS OCR ("REPORT OF THE") and "Sir, I have" read as surname + initials otherwise.
_AUTHOR = re.compile(
    r"(?:^|\n|[.;]\s+)[A-Z][a-z'\-]{2,},?\s+(?:(?:[A-Z]\.){1,3},?|[A-Z]{1,3}[.,])(?:\s|$)", re.MULTILINE)
_YEAR_NEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
AUTHOR_YEAR_WINDOW = 160   # a reference entry states its year within a line or two of its author


def author_entries(text: str) -> int:
    """Author openings followed by a year within AUTHOR_YEAR_WINDOW characters. Speaker
    lists in minutes ("Tobin, M.P.") and staff rosters ("Anderson, R. C., M.D.") open
    the same way but carry no year; bibliography entries do."""
    n = 0
    for m in _AUTHOR.finditer(text):
        if _YEAR_NEAR.search(text, m.end(), m.end() + AUTHOR_YEAR_WINDOW):
            n += 1
    return n


_INDEX_LINE = re.compile(r"^[A-Za-z][^\n]{2,60},\s*\d{1,4}(,\s*\d{1,4})*\s*$", re.MULTILINE)  # "Tuberculosis, 12, 45"
# "Findings .... 15" / "Findings 15": a line with a letter that ends in whitespace + 1-4 digits.
# Anchored at line start so each line is scanned once (the unanchored form backtracked
# quadratically: 23 ms/page on real OCR against 0.05 ms for every other rule).
_LEADER = re.compile(r"^(?=[^\n]*[A-Za-z])[^\n]*[ \t]\d{1,4}[ \t]*$|^[^\n]*\.{3,}[ \t]*\d{1,4}[ \t]*$", re.MULTILINE)
_PAGE_ONLY = re.compile(r"^\s*([ivxlc]{1,6}|\d{1,4})\s*$", re.IGNORECASE | re.MULTILINE)


class DatabaseBusy(RuntimeError):
    """Another connection holds civic.db; the ingest refuses to start."""


def signals(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    n = max(len(lines), 1)
    return {
        "n_lines": len(lines),
        "chars": len(text),
        "toc": bool(_TOC.search(text)),
        "transmittal": bool(_TRANSMITTAL.search(text)),
        "index_head": bool(_INDEX_HEAD.search(text)),
        "ref_head": bool(_REF_HEAD.search(text)),
        "numbered": len(_NUMBERED.findall(text)),
        "cites": len(_CITE.findall(text)),
        "authors": author_entries(text),
        "index_lines": len(_INDEX_LINE.findall(text)),
        "leader_share": len(_LEADER.findall(text)) / n,
        "page_only_share": len(_PAGE_ONLY.findall(text)) / n,
    }


def zones(leaf_index: int, n_leaves: int) -> tuple[bool, bool]:
    front = leaf_index < max(FRONT_MIN, math.ceil(FRONT_SHARE * n_leaves))
    back = leaf_index > n_leaves - 1 - max(BACK_MIN, math.ceil(BACK_SHARE * n_leaves))
    return front, back


def classify(leaf_index: int, n_leaves: int, text: str) -> tuple[str, str]:
    """(section_class, method). The method names the deciding rule so sampled pages
    can be checked rule by rule."""
    s = signals(text or "")
    front_zone, back_zone = zones(leaf_index, n_leaves)
    # Back matter: reference/index evidence anywhere in the item (per-chapter reference
    # lists included); weaker list evidence only in the back zone. A reference list
    # needs citation evidence (page ranges next to years, or author-name openings),
    # never a bare numbered list or a year beside a colon.
    if s["ref_head"] and (s["cites"] >= 1 or s["authors"] >= 2 or s["numbered"] >= 3):
        return "back", "references_heading"
    if s["index_head"] or s["index_lines"] >= 8:
        return "back", "index"
    if s["cites"] >= 3 or (s["cites"] >= 2 and s["authors"] >= 2) or s["authors"] >= 5:
        return "back", "reference_list"
    if back_zone and (s["numbered"] >= 5 or s["index_lines"] >= 4 or s["page_only_share"] >= 0.3):
        return "back", "back_zone_list"
    # Front matter: only in the front zone.
    if front_zone:
        if leaf_index < 2:
            return "front", "cover"
        if s["transmittal"]:
            return "front", "transmittal"
        if s["toc"] or (s["n_lines"] >= 3 and s["leader_share"] >= 0.3):
            return "front", "contents"
        if s["chars"] < 400 and s["n_lines"] <= 12:
            return "front", "title_page"
        if s["page_only_share"] >= 0.3:
            return "front", "front_zone_list"
    return "body", "default"


def _excerpt(text: str, n: int = 240) -> str:
    return " ".join((text or "").split())[:n]


class _Reservoir:
    """Deterministic reservoir sample of k rows per class."""

    def __init__(self, k: int, seed: int):
        self.k = k
        self.rng = random.Random(seed)
        self.seen: Counter = Counter()
        self.kept: dict = {c: [] for c in CLASSES}

    def offer(self, cls: str, row: dict) -> None:
        self.seen[cls] += 1
        bucket = self.kept[cls]
        if len(bucket) < self.k:
            bucket.append(row)
        else:
            j = self.rng.randrange(self.seen[cls])
            if j < self.k:
                bucket[j] = row


def _probe_exclusive(conn: sqlite3.Connection) -> None:
    """Fail fast if another connection holds the db (we need to switch journal mode)."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError as exc:
        raise DatabaseBusy(f"civic.db is held by another connection ({exc}); close the API/other "
                           "readers and rerun") from exc


def _fmt_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def classify_db(conn: sqlite3.Connection, *, sample: int = 20, seed: int = 13, limit: Optional[int] = None,
                batch: int = BATCH, progress: Callable[[str], None] = print) -> dict:
    """Classify every page with text (or the first `limit` in item/leaf order); write
    the two columns in batches; return counts, samples, and timing."""
    _probe_exclusive(conn)
    prior_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    if mode != "wal":
        raise DatabaseBusy(f"could not switch to WAL (journal_mode stayed {mode}); another connection is open")
    conn.execute("PRAGMA synchronous=NORMAL")
    t0 = time.perf_counter()
    try:
        n_leaves = {item: n for item, n in conn.execute("SELECT item_id, MAX(leaf_index) + 1 FROM pages GROUP BY item_id")}
        titles = dict(conn.execute("SELECT item_id, title FROM items"))
        pages = conn.execute("SELECT page_id, item_id, leaf_index FROM pages ORDER BY item_id, leaf_index").fetchall()
        total_pages = len(pages)
        if limit is not None:
            pages = pages[:limit]
        counts: Counter = Counter()
        methods: Counter = Counter()
        no_text = 0
        reservoir = _Reservoir(sample, seed)
        updates: list[tuple] = []

        def flush() -> None:
            if updates:
                conn.executemany("UPDATE pages SET section_class = ?, section_method = ? WHERE page_id = ?", updates)
                conn.commit()
                updates.clear()

        for i, (page_id, item_id, leaf) in enumerate(pages, start=1):
            text = "\n".join(t for (t,) in conn.execute(
                "SELECT text FROM passages WHERE page_id = ? ORDER BY char_start", (page_id,)) if t)
            if not text.strip():
                no_text += 1
            else:
                cls, method = classify(leaf or 0, n_leaves.get(item_id, 1), text)
                counts[cls] += 1
                methods[method] += 1
                reservoir.offer(cls, {"page_id": page_id, "item_id": item_id, "title": titles.get(item_id),
                                      "leaf": leaf, "n_leaves": n_leaves.get(item_id), "method": method,
                                      "excerpt": _excerpt(text)})
                updates.append((cls, method, page_id))
            if len(updates) >= batch:
                flush()
            if i % 10_000 == 0 or i == len(pages):
                elapsed = time.perf_counter() - t0
                rate = i / elapsed if elapsed else 0.0
                progress(f"pages {i}/{len(pages)}  {rate:,.0f} pages/s  elapsed {_fmt_eta(elapsed)}  "
                         f"ETA {_fmt_eta((len(pages) - i) / rate) if rate else '?'}")
        flush()
        elapsed = time.perf_counter() - t0
        unclassified = conn.execute("SELECT COUNT(*) FROM pages WHERE section_class IS NULL").fetchone()[0]
        passages_by_class = dict(conn.execute(
            "SELECT COALESCE(g.section_class, 'unclassified'), COUNT(*) FROM passages p "
            "JOIN pages g ON g.page_id = p.page_id GROUP BY 1"))
    finally:
        conn.commit()
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(f"PRAGMA journal_mode={prior_mode}")   # checkpoints and removes the WAL
    rate = len(pages) / elapsed if elapsed else 0.0
    return {
        "pages_walked": len(pages),
        "pages_total": total_pages,
        "pages_classified": sum(counts.values()),
        "pages_no_text_in_walk": no_text,
        "pages_unclassified_null": unclassified,
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "passages_by_class": passages_by_class,
        "methods": dict(methods.most_common()),
        "samples": {c: sorted(reservoir.kept[c], key=lambda r: (r["item_id"], r["leaf"])) for c in CLASSES},
        "thresholds": {"front_share": FRONT_SHARE, "front_min": FRONT_MIN, "back_share": BACK_SHARE, "back_min": BACK_MIN},
        "seed": seed,
        "limit": limit,
        "timing": {"elapsed_s": round(elapsed, 1), "pages_per_s": round(rate, 1),
                   "projected_total_s": round(total_pages / rate, 1) if rate else None},
    }


def write_report(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sections_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Phase 13 section classifier report", "",
             "Deterministic front / body / back classification of every page with text, from leaf",
             "position and text signals. Thresholds fixed a priori; no labels used. Samples are a",
             f"seeded reservoir sample (seed {result['seed']}) so the same db reproduces the same rows.", ""]
    if result.get("limit"):
        lines += [f"NOTE: timing run limited to the first {result['limit']} pages in item/leaf order.", ""]
    t = result["timing"]
    lines += ["## Counts", "",
              f"- pages walked: {result['pages_walked']} of {result['pages_total']} "
              f"({t['pages_per_s']} pages/s, {t['elapsed_s']} s)",
              f"- pages classified: {result['pages_classified']}",
              f"- pages with no text (left NULL): {result['pages_no_text_in_walk']} in this walk; "
              f"{result['pages_unclassified_null']} NULL in the table"]
    for c in CLASSES:
        lines.append(f"- {c}: {result['counts'][c]} pages, {result['passages_by_class'].get(c, 0)} passages")
    lines += ["", "## Deciding rule", "", "| method | pages |", "| --- | ---: |"]
    for m, n in result["methods"].items():
        lines.append(f"| {m} | {n} |")
    for c in CLASSES:
        lines += ["", f"## Sample: {c} ({len(result['samples'][c])} pages)", ""]
        for r in result["samples"][c]:
            title = " ".join(str(r["title"] or "").split())[:70]
            lines.append(f"- `{r['page_id']}` leaf {r['leaf']}/{r['n_leaves']} [{r['method']}] {title}")
            lines.append(f"  > {r['excerpt']}")
    (out_dir / "sections_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: Path, *, out_dir: Path = Path("reports/phase13"), sample: int = 20, seed: int = 13,
        limit: Optional[int] = None) -> dict:
    db_path = db.resolve_db_path(config_path)
    if not Path(db_path).exists():
        # Never create a fresh db here: a wrong path (env var not set, .env not loaded)
        # would otherwise produce an empty file and a run that classifies nothing.
        raise FileNotFoundError(f"civic.db not found at {db_path}; set CIVIC_DB_PATH or fix [index].db_path")
    conn = db.init_db(db_path)   # migrates the two columns if missing
    try:
        result = classify_db(conn, sample=sample, seed=seed, limit=limit)
    finally:
        conn.close()
    write_report(result, out_dir)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    from dotenv import load_dotenv  # CLI only: picks up CIVIC_DB_PATH from .env; never overrides a set variable
    load_dotenv()
    p = argparse.ArgumentParser(description="Classify pages as front/body/back matter into civic.db (one-time ingest step).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default="reports/phase13", type=Path)
    p.add_argument("--sample", default=20, type=int)
    p.add_argument("--limit", default=None, type=int, help="classify only the first N pages (timing run)")
    args = p.parse_args(argv)
    try:
        result = run(args.config, out_dir=args.out, sample=args.sample, limit=args.limit)
    except (DatabaseBusy, FileNotFoundError) as exc:
        print(f"aborted: {exc}")
        return 2
    print(json.dumps({"pages_walked": result["pages_walked"], "counts": result["counts"],
                      "passages_by_class": result["passages_by_class"], "timing": result["timing"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
