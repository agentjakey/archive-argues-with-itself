"""Phase 5 prep: a bounded second source through the adapter contract (docs/INTEROP.md).

    python scripts/v2/second_source.py --prefix www.hc-sc.gc.ca/hc-ps/tobac-tabac/ --from 2005 --to 2010 --limit 30

Fetches the Wayback captures (sources.wayback, every request through the allowlist), writes them to
data/sources/<name>.jsonl and stores them in the registry as their own archive. Staging only: nothing
here is published.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.registry import build  # noqa: E402
from archive_debugger.sources.wayback import WaybackPrefix  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--from", dest="first", type=int, required=True)
    ap.add_argument("--to", dest="last", type=int, required=True)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--name", default="wayback-hc-tobacco")
    args = ap.parse_args(argv)
    records = list(WaybackPrefix(args.prefix, args.first, args.last, args.limit).records())
    out = REPO / "data" / "sources" / f"{args.name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps({**asdict(r), "problems": r.problems()}, ensure_ascii=True) + "\n" for r in records),
                   encoding="utf-8")
    counts = build.add_source_records(build.open_registry(REPO / "data" / "registry" / "registry.db"), records,
                                      collection=args.name)
    with_pub = sum(1 for r in records if r.publication.year is not None)
    gaps = [r.capture.year - r.publication.year for r in records if r.publication.year is not None]
    print(json.dumps({"records": len(records), **counts, "with_publication_date": with_pub,
                      "capture_minus_publication_years": sorted(gaps)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
