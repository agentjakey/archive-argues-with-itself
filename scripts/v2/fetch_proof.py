"""Proof that the small full-text files give the same pages as today's compile, and what they save.

    python scripts/v2/fetch_proof.py --db data/exploration/microlog/civic_microlog.db --items 200

Today's corpus (the microlog collection) was compiled from each item's <name>_djvu.xml: one page per
OBJECT, its leaf the object's position. The whole-collection fetch takes three small files instead:
<name>_hocr_searchtext.txt.gz, <name>_hocr_pageindex.json.gz and <name>_page_numbers.json, and the
compile job (archive_debugger.jobs.compile.item_pages) cuts the pages from them. For a seeded random
sample of today's items this script fetches the small files, cuts the pages, and compares them with
the pages in today's database:

  - page ids: the same set of <identifier>#<leaf>;
  - page text: for each page, the word overlap (Jaccard over word sets) between the new page's text
    and today's page text rebuilt from its passages; the same score against the neighbouring leaves
    shows whether a mapping is shifted by one.

Bytes per item come from the item's metadata (file sizes as archive.org lists them): before, the
djvu.xml today's compile read; after, the three small files. Writes one JSON line per item to
reports/v2/scale/fetch_proof.jsonl and a summary to reports/v2/scale/fetch_proof.json. Requests go
through the catalogue's polite network module (identified, at most two at a time, backoff)."""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sqlite3
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.catalogue import fulltext, net  # noqa: E402
from archive_debugger.jobs import compile as compile_job  # noqa: E402

OUT = REPO / "reports" / "v2" / "scale"
WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def words(text: str) -> set:
    return {w.lower() for w in WORD.findall(text or "")}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def old_pages(conn: sqlite3.Connection, ident: str) -> dict:
    """{page_id: text} for today's pages, the text rebuilt from the passages' character spans."""
    pages = {pid: "" for pid, in conn.execute("SELECT page_id FROM pages WHERE item_id = ?", (ident,))}
    spans: dict = {}
    for pid, start, end, text in conn.execute(
            "SELECT page_id, char_start, char_end, text FROM passages WHERE item_id = ? ORDER BY page_id, char_start",
            (ident,)):
        spans.setdefault(pid, []).append((start or 0, end or 0, text or ""))
    for pid, parts in spans.items():
        out, reached = [], 0
        for start, end, text in parts:
            if end <= reached:
                continue
            skip = max(0, reached - start)
            out.append(text[skip:] if skip < len(text) else "")
            reached = max(reached, end)
        pages[pid] = " ".join(out)
    return pages


def leaf(page_id: str) -> int:
    return int(page_id.rsplit("#", 1)[1])


def one(ident: str, djvu_name: str, conn_path: str) -> dict:
    meta = json.loads(net.get(fulltext.METADATA.format(ident=ident)).decode("utf-8"))
    sizes = {f["name"]: int(f.get("size") or 0) for f in meta.get("files") or []}
    named = djvu_name.split("/")[-1].split("__", 1)[-1]
    row = {"identifier": ident, "djvu_xml_bytes": sizes.get(named) or
           next((s for n, s in sizes.items() if n.endswith("_djvu.xml")), 0)}
    names = {}
    for name in sizes:
        for role, suffix in (("searchtext", fulltext.SEARCHTEXT), ("pageindex", fulltext.PAGEINDEX),
                             ("page_numbers", fulltext.PAGE_NUMBERS)):
            if name.endswith(suffix):
                names[role] = name
    row["small_bytes"] = sum(sizes[n] for n in names.values())
    row["small_files"] = sorted(names)
    row["djvu_txt_bytes"] = next((s for n, s in sizes.items() if n.endswith(fulltext.DJVU)), 0)
    row["hocr_html_bytes"] = next((s for n, s in sizes.items() if n.endswith("_hocr.html")), 0)
    if "searchtext" not in names or "pageindex" not in names:
        row["result"] = "no small files: falls back"
        return row
    files = {role: net.get(fulltext.DOWNLOAD.format(ident=ident, name=n)) for role, n in names.items()}
    searchtext = gzip.decompress(files["searchtext"]).decode("utf-8", errors="replace")
    pageindex = json.loads(gzip.decompress(files["pageindex"]))
    page_numbers = json.loads(files["page_numbers"]) if "page_numbers" in files else {}
    new, reason = compile_job.item_pages(ident, searchtext, pageindex, page_numbers)
    conn = sqlite3.connect(conn_path)
    old = old_pages(conn, ident)
    conn.close()
    row["old_pages"], row["new_pages"] = len(old), len(new)
    if reason:
        row["result"] = f"compile skips it: {reason}"
        return row
    new_text = {p["page_id"]: p["_text"] for p in new}
    row["same_ids"] = set(new_text) == set(old)
    shared = sorted(set(new_text) & set(old), key=leaf)
    scores, shifted = [], 0
    old_by_leaf = {leaf(p): t for p, t in old.items()}
    for pid in shared:
        a = words(new_text[pid])
        here = jaccard(a, words(old[pid]))
        scores.append(here)
        k = leaf(pid)
        nearby = max((jaccard(a, words(old_by_leaf[j])) for j in (k - 1, k + 1) if j in old_by_leaf), default=0.0)
        if len(a) >= 20 and nearby > here + 0.2:
            shifted += 1
    texted = [s for pid, s in zip(shared, scores) if len(words(new_text[pid])) >= 20]
    row["pages_compared"] = len(shared)
    row["median_jaccard"] = round(statistics.median(texted), 3) if texted else None
    row["pages_jaccard_ge_0_8"] = sum(1 for s in texted if s >= 0.8)
    row["pages_with_text"] = len(texted)
    row["pages_closer_to_a_neighbour"] = shifted
    row["result"] = "match" if row["same_ids"] and shifted == 0 and (not texted or row["median_jaccard"] >= 0.8) else "differs"
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--items", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261102)
    args = ap.parse_args(argv)
    conn = sqlite3.connect(args.db)
    items = conn.execute("SELECT item_id, ocr_file_ref FROM items WHERE ocr_format = 'DjVuXML' ORDER BY item_id").fetchall()
    conn.close()
    sample = random.Random(args.seed).sample(items, min(args.items, len(items)))
    rows = []
    with ThreadPoolExecutor(max_workers=net.START_CONCURRENCY) as pool:
        for row in pool.map(lambda it: _safe(it, args.db), sample):
            rows.append(row)
            print(f"{len(rows):4d} {row['identifier']:40s} {row['result']}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "fetch_proof.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    with_small = [r for r in rows if r.get("small_bytes") and r.get("djvu_xml_bytes")]
    compared = [r for r in rows if "same_ids" in r]
    summary = {
        "db": args.db, "items": len(rows), "seed": args.seed,
        "results": {k: sum(1 for r in rows if r["result"] == k) for k in sorted({r["result"] for r in rows})},
        "same_page_ids": sum(1 for r in compared if r["same_ids"]), "compared": len(compared),
        "pages_compared": sum(r["pages_compared"] for r in compared),
        "pages_with_text": sum(r["pages_with_text"] for r in compared),
        "pages_jaccard_ge_0_8": sum(r["pages_jaccard_ge_0_8"] for r in compared),
        "pages_closer_to_a_neighbour": sum(r["pages_closer_to_a_neighbour"] for r in compared),
        "median_item_jaccard": statistics.median([r["median_jaccard"] for r in compared if r["median_jaccard"] is not None])
        if compared else None,
        "bytes_per_item": {
            "items": len(with_small),
            "before_djvu_xml_mean": round(statistics.mean(r["djvu_xml_bytes"] for r in with_small)) if with_small else None,
            "before_djvu_xml_median": round(statistics.median(r["djvu_xml_bytes"] for r in with_small)) if with_small else None,
            "after_small_files_mean": round(statistics.mean(r["small_bytes"] for r in with_small)) if with_small else None,
            "after_small_files_median": round(statistics.median(r["small_bytes"] for r in with_small)) if with_small else None,
            "djvu_txt_mean": round(statistics.mean(r["djvu_txt_bytes"] for r in with_small)) if with_small else None,
            "hocr_html_mean": round(statistics.mean(r["hocr_html_bytes"] for r in with_small)) if with_small else None,
        },
    }
    (OUT / "fetch_proof.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


def _safe(item, db):
    ident, ref = item
    try:
        return one(ident, ref or "", db)
    except Exception as exc:          # one failing item is reported, the proof goes on
        return {"identifier": ident, "result": f"error: {str(exc)[:160]}"}


if __name__ == "__main__":
    sys.exit(main())
