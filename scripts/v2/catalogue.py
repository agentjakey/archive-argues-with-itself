"""The whole collection's catalogue (Phase 4 prep).

  fetch     every item's catalogue record with the scrape API (resumes; polite; stops on repeated 429/503)
  write     the records, checked against their page checksums, into catalogue.jsonl.gz
  upload    the raw pages, the catalogue and their checksums to the private R2 bucket
  fulltext  every item's OCR text, page by page, to data/fulltext and R2 (resumes; polite)
  status    one line: how far the full-text fetch has got and its projected finish (--r2: read from R2,
            with the shards built so far; works from any machine with the R2 credentials)
  browse    the registry as static files for the site's /catalogue/ page (build/catalogue-data)

    python scripts/v2/catalogue.py fetch
    python scripts/v2/catalogue.py write
    python scripts/v2/catalogue.py upload
    python scripts/v2/catalogue.py fulltext --stream --order-r2 --max-minutes 340 --concurrency 4 --max-concurrency 8
    python scripts/v2/catalogue.py status --r2
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
    ap.add_argument("command", choices=["fetch", "write", "upload", "fulltext", "status", "browse"])
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--limit", type=int, default=None, help="fulltext: at most this many items this run")
    ap.add_argument("--no-r2", action="store_true", help="fulltext: keep files locally only")
    ap.add_argument("--ids", type=Path, default=None, help="fulltext: only these identifiers (one per line), first")
    ap.add_argument("--stream", action="store_true", help="fulltext: files go to R2 only, nothing kept on disk")
    ap.add_argument("--order-r2", action="store_true", help="fulltext: the fetch order (every identifier) from R2")
    ap.add_argument("--max-minutes", type=float, default=None, help="fulltext: stop cleanly after this long")
    ap.add_argument("--concurrency", type=int, default=None, help="fulltext: requests at once to start with")
    ap.add_argument("--max-concurrency", type=int, default=None, help="fulltext: the most it may rise to (never above 8)")
    ap.add_argument("--step", type=int, default=2, help="fulltext: how far it rises after each quiet hour")
    ap.add_argument("--pause", type=float, default=None, help="fulltext: seconds each request thread waits after a request")
    ap.add_argument("--sync-every", type=int, default=None, help="fulltext: manifest lines per R2 chunk")
    ap.add_argument("--out", type=Path, default=None, help="fulltext: the local folder (default data/fulltext)")
    ap.add_argument("--r2", action="store_true", help="status: read the status from R2")
    args = ap.parse_args(argv)
    if args.command == "fetch":
        index = fetch.fetch_catalogue(f"collection:{args.collection}", CACHE)
        print(json.dumps({"pages": len(index["pages"]), "complete": index["complete"],
                          "records": sum(p["items"] for p in index["pages"])}))
        return 0 if index["complete"] else 1
    if args.command == "write":
        print(json.dumps(fetch.write_catalogue(CACHE, OUT)))
        return 0
    if args.command == "status" and args.r2:
        return status_from_r2()
    if args.command == "status":
        path = REPO / "data" / "fulltext" / "status.json"
        if not path.exists():
            print("no status yet: the full-text fetch has not written data/fulltext/status.json")
            return 1
        s = json.loads(path.read_text(encoding="utf-8"))
        c = s["concurrency"]
        print(f"{s['at']}: {s['done']:,} of {s['total']:,} items ({100 * s['done'] / max(1, s['total']):.1f}%), "
              f"{s['per_hour_last_hour']}/h last hour, {s['per_hour_last_day']}/h last day, "
              f"projected finish {s['projected_finish'] or 'unknown'}; concurrency {c['limit']}, "
              f"{'no server error yet' if c['since_problem_s'] is None else str(c['since_problem_s'] // 60) + ' min since the last server error'}")
        return 0
    if args.command == "browse":
        import sqlite3
        from archive_debugger.catalogue import browse
        index = json.loads((CACHE / "pages.json").read_text(encoding="utf-8"))
        note = {"fetched_at": index["pages"][-1]["fetched_at"], "text": (
            f"The list comes from the Internet Archive's catalogue of the {args.collection} collection "
            f"({sum(p['items'] for p in index['pages']):,} records, fetched {index['pages'][-1]['fetched_at'][:10]} with "
            "its public scrape API), plus the items this site indexes from other collections. Places and issuers "
            "are read from each record's publisher and creator by the site's rules; a place we could not read is "
            "shown as unknown. A year read from a title is shown as such, never as the catalogue's date.")}
        print(json.dumps(browse.export(sqlite3.connect(REPO / "data" / "registry" / "registry.db"),
                                       REPO / "build" / "catalogue-data", source_note=note)))
        return 0
    from archive_debugger.local_env import load_local_env
    from archive_debugger.jobs.store import R2Store
    load_local_env(log=None)
    if args.command == "fulltext":
        import os
        import time
        from archive_debugger.catalogue import fulltext, net
        store = None if args.no_r2 else R2Store()
        if args.concurrency or args.max_concurrency:
            start = args.concurrency or net.START_CONCURRENCY
            net.configure(start, args.max_concurrency or start, step=args.step, log=print)
        if args.pause is not None:
            net.PAUSE_S = args.pause
        order = REPO / "data" / "fulltext" / "order.txt"     # shard by shard (shard_builder.py order)
        if args.order_r2:
            # The cloud runners have no catalogue cache: the order on R2 lists every identifier.
            raw = store.get(fulltext.ORDER_KEY) if store.head(fulltext.ORDER_KEY) else None
            if raw is None:
                raise SystemExit(f"{fulltext.ORDER_KEY} is not on R2: run shard_builder.py order --upload")
            idents = list(dict.fromkeys(l.strip() for l in raw.decode("utf-8").splitlines() if l.strip()))
        else:
            idents = [r["identifier"] for r in fetch.records(CACHE)
                      if (r.get("mediatype") or "texts") == "texts"]
        if args.order_r2:
            pass                                               # already in order
        elif args.ids:
            wanted = [l.strip() for l in args.ids.read_text(encoding="utf-8").splitlines() if l.strip()]
            idents = [i for i in wanted if i in set(idents)]
        elif order.exists():
            known = set(idents)
            first = [l.strip() for l in order.read_text(encoding="utf-8").splitlines() if l.strip() in known]
            idents = list(dict.fromkeys(first + sorted(known)))
        else:
            idents = sorted(set(idents))
        deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
        extra = {"sync_every": args.sync_every} if args.sync_every else {}
        counts = fulltext.run(idents, args.out or REPO / "data" / "fulltext", store=store, stop_after=args.limit,
                              keep_local=not args.stream, deadline=deadline,
                              runner=os.environ.get("GITHUB_RUN_ID") and
                              f"actions run {os.environ['GITHUB_RUN_ID']} attempt {os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
                              or os.environ.get("COMPUTERNAME") or "local", **extra)
        print(json.dumps(counts))
        return 1 if counts.get("stopped") else 0
    store = R2Store()
    files = [CACHE / "pages.json", *sorted(CACHE.glob("page-*.json.gz")), OUT]
    for path in files:
        key = f"{R2_PREFIX}/{path.relative_to(REPO / 'data' / 'catalogue').as_posix()}"
        meta = store.put(key, path.read_bytes())
        print(f"{key}: {meta['bytes']} bytes, sha256 {meta['sha256'][:16]}")
    return 0


def status_from_r2() -> int:
    """Two lines from R2 alone: the fetch (its last status, written at every manifest sync) and the
    shards (built on R2 under shards/v1/, of the plan's)."""
    from datetime import datetime, timezone
    from archive_debugger.local_env import load_local_env
    from archive_debugger.jobs.store import R2Store
    from archive_debugger.catalogue import fulltext
    load_local_env(log=None)
    store = R2Store()
    raw = store.get(fulltext.STATUS_KEY) if store.head(fulltext.STATUS_KEY) else None
    if raw is None:
        print("no status on R2 yet")
    else:
        s = json.loads(raw)
        c = s.get("concurrency") or {}
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(s["at"].replace("Z", "+00:00"))).total_seconds() / 60
        print(f"fetch {s['at']} ({age:.0f} min ago, {s.get('runner') or '?'}): {s['done']:,} of {s['total']:,} items "
              f"({100 * s['done'] / max(1, s['total']):.1f}%), {s['per_hour_last_hour']}/h last hour, "
              f"{s['per_hour_last_day']}/h last day, projected finish {s['projected_finish'] or 'unknown'}; "
              f"concurrency {c.get('limit')}, " + ("no server error yet" if c.get("since_problem_s") is None
                                                  else f"{c['since_problem_s'] // 60} min since the last server error"))
    plan = json.loads((REPO / "config" / "shards" / "plan.json").read_text(encoding="utf-8"))["shards"]
    built = sorted({k.split("/")[2] for k in store.list("shards/v1/") if k.endswith("/manifest.json") and k.count("/") == 3})
    planned = {s["shard_id"] for s in plan}
    done = [b for b in built if b in planned]
    print(f"shards: {len(done)} of {len(planned)} built on R2" + (f" (latest: {', '.join(done[-3:])})" if done else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
