"""Whole-collection sizing from a seeded random sample of governmentpublications items (Phase 2
Part A).

    python scripts/v2/sample_collection.py --size 200 --seed 20261101

Steps, each cached on disk so a rerun makes no network calls:
  1. list every item identifier in the collection (the scrape API, 10,000 per page);
  2. draw `size` identifiers at random with the seed;
  3. read each item's metadata (the metadata API) and download its DjVuTXT, when it has one;
  4. measure per item: pages, OCR bytes, pages with text, passages under the corpus chunker
     (`ingest/ocr.py`, 300 words with 40 overlap), OCR quality per passage, language and year.

Requests are polite: the harvest's identified user agent, one at a time, a pause after each
network call, retries with backoff, and nothing fetched twice. Writes
reports/v2/sizing/sample_items.jsonl and sample_summary.json; the extrapolation is in
scripts/v2/size_collection.py."""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.harvest import discover, explore, fetch  # noqa: E402
from archive_debugger.ingest import ocr  # noqa: E402

OUT = REPO / "reports" / "v2" / "sizing"
CACHE = REPO / "reports" / "v2" / "raw" / "collection_sample"
COLLECTION = "governmentpublications"
CONTACT = "hello@archiveargues.org"


def context() -> dict:
    return {"cache_dir": CACHE / "json", "transport": explore.default_transport, "sleeper": time.sleep,
            "rng": random.Random(0), "headers": {"User-Agent": explore.user_agent(CONTACT)}}


def all_identifiers(ctx: dict) -> tuple[list, dict]:
    items, meta = explore.scrape_all(f"collection:{COLLECTION}", fields="identifier", count=10000,
                                     cache_dir=ctx["cache_dir"], transport=ctx["transport"], sleeper=ctx["sleeper"],
                                     rng=ctx["rng"], headers=ctx["headers"])
    return sorted({it["identifier"] for it in items if it.get("identifier")}), meta


def measure_text(raw: str) -> dict:
    pages = ocr.parse_djvutxt(raw)
    with_text = [p for p in pages if p.strip()]
    passages = [ch for p in with_text for ch in ocr.chunk_within_page(p)]
    buckets = {"high": 0, "medium": 0, "low": 0}
    for ch in passages:
        buckets[ocr.quality_bucket(ocr.ocr_quality(ch["text"]))] += 1
    # archive.org's public _djvu.txt carries no page breaks (measured: none in any sampled file), so
    # "text_pages" is 1 and the passages here are chunks of the whole item; size_collection.py
    # estimates passages from words and from scanned pages instead.
    return {"text_pages": len(pages), "pages_with_text": len(with_text), "ocr_bytes": len(raw.encode("utf-8")),
            "words": len(raw.split()),
            "passages": len(passages), "passage_quality": buckets,
            "passage_words": sum(ch["token_count"] for ch in passages)}


def languages_of(meta: dict) -> list:
    value = (meta.get("metadata") or {}).get("language")
    if value is None:
        return []
    return [str(v).lower() for v in (value if isinstance(value, list) else [value])]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = context()
    ids, listing = all_identifiers(ctx)
    print(f"{len(ids)} identifiers in {COLLECTION} (scrape total {listing.get('total')}, {listing.get('pages')} pages)")
    sample = random.Random(args.seed).sample(ids, args.size)
    rows = []
    for n, identifier in enumerate(sample, 1):
        try:
            meta = discover.fetch_metadata(identifier, ctx=ctx)
        except explore.ScrapeError as exc:
            # archive.org answered with an error field instead of the item's metadata: counted, kept
            rows.append({"identifier": identifier, "metadata_error": str(exc)[-200:], "imagecount": None,
                         "year": None, "languages": [], "has_djvutxt": False})
            continue
        md = meta.get("metadata") or {}
        row = {"identifier": identifier, "imagecount": fetch.page_count_of(meta), "year": discover.meta_year(meta),
               "date_raw": md.get("date"), "languages": languages_of(meta), "mediatype": md.get("mediatype"),
               "collections": discover.collections_of(meta), "has_djvutxt": False}
        djvu = fetch.find_djvutxt(meta)
        if djvu and djvu.get("md5"):
            try:
                path, _ = fetch.download_file(identifier, djvu, CACHE / "files", delay=1.0)
            except Exception as exc:     # a server error on one file: counted, never retried in a loop
                row["download_error"] = str(exc)[-200:]
                rows.append(row)
                time.sleep(5.0)
                continue
            row["has_djvutxt"] = True
            row.update(measure_text(path.read_text(encoding="utf-8", errors="replace")))
        rows.append(row)
        if n % 20 == 0:
            print(f"{n} of {len(sample)} items measured")
    with (OUT / "sample_items.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    texts = [r for r in rows if r["has_djvutxt"]]
    summary = {
        "collection": COLLECTION, "identifiers": len(ids), "seed": args.seed, "sample": len(rows),
        "with_djvutxt": len(texts), "undated": sum(1 for r in rows if r["year"] is None and not r.get("metadata_error")),
        "metadata_errors": sum(1 for r in rows if r.get("metadata_error")),
        "download_errors": sum(1 for r in rows if r.get("download_error")),
        "median_pages": statistics.median([r["imagecount"] for r in rows if r["imagecount"]]) if rows else None,
        "languages": dict(sorted(((lang, sum(1 for r in rows if lang in r["languages"]))
                                  for lang in {l for r in rows for l in r["languages"]}), key=lambda kv: -kv[1])),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / "sample_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
