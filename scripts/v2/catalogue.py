"""The whole collection's catalogue (Phase 4 prep).

  fetch     every item's catalogue record with the scrape API (resumes; polite; stops on repeated 429/503)
  write     the records, checked against their page checksums, into catalogue.jsonl.gz
  upload    the raw pages, the catalogue and their checksums to the private R2 bucket
  fulltext  every item's OCR text, page by page, to data/fulltext and R2 (resumes; polite)

    python scripts/v2/catalogue.py fetch
    python scripts/v2/catalogue.py write
    python scripts/v2/catalogue.py upload
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.catalogue import fetch  # noqa: E402

COLLECTION = "governmentpublications"
CACHE = REPO / "data" / "catalogue" / "scrape"
OUT = REPO / "data" / "catalogue" / "catalogue.jsonl.gz"
R2_PREFIX = "catalogue/v1"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["fetch", "write", "upload", "fulltext"])
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--limit", type=int, default=None, help="fulltext: at most this many items this run")
    ap.add_argument("--no-r2", action="store_true", help="fulltext: keep files locally only")
    args = ap.parse_args(argv)
    if args.command == "fetch":
        index = fetch.fetch_catalogue(f"collection:{args.collection}", CACHE)
        print(json.dumps({"pages": len(index["pages"]), "complete": index["complete"],
                          "records": sum(p["items"] for p in index["pages"])}))
        return 0 if index["complete"] else 1
    if args.command == "write":
        print(json.dumps(fetch.write_catalogue(CACHE, OUT)))
        return 0
    from archive_debugger.local_env import load_local_env
    from archive_debugger.jobs.store import R2Store
    load_local_env(log=None)
    if args.command == "fulltext":
        from archive_debugger.catalogue import fulltext
        idents = [r["identifier"] for r in fetch.records(CACHE)
                  if (r.get("mediatype") or "texts") == "texts"]
        counts = fulltext.run(sorted(set(idents)), REPO / "data" / "fulltext",
                              store=None if args.no_r2 else R2Store(), stop_after=args.limit)
        print(json.dumps(counts))
        return 1 if counts.get("stopped") else 0
    store = R2Store()
    files = [CACHE / "pages.json", *sorted(CACHE.glob("page-*.json.gz")), OUT]
    for path in files:
        key = f"{R2_PREFIX}/{path.relative_to(REPO / 'data' / 'catalogue').as_posix()}"
        meta = store.put(key, path.read_bytes())
        print(f"{key}: {meta['bytes']} bytes, sha256 {meta['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
