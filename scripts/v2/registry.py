"""Build the normalized registry (docs/formats/registry.md) from files.

    python scripts/v2/registry.py build --catalogue data/catalogue/catalogue.jsonl.gz --indexed pilot,microlog
    python scripts/v2/registry.py stats

Writes data/registry/registry.db (gitignored). Rebuilding from the same files gives the same rows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.registry import build  # noqa: E402

DB = REPO / "data" / "registry" / "registry.db"
REGISTER = REPO / "config" / "governance" / "policies.jsonl"


def stats(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "documents": q("SELECT COUNT(*) FROM documents"),
        "collections": q("SELECT COUNT(*) FROM collections"),
        "coverage": {r[0]: r[1] for r in conn.execute("SELECT state, COUNT(DISTINCT doc_id) FROM coverage GROUP BY state")},
        "catalogue_dated": q("SELECT COUNT(*) FROM dates WHERE kind = 'catalogue' AND year IS NOT NULL"),
        "derived_dates": q("SELECT COUNT(*) FROM dates WHERE kind = 'derived'"),
        "jurisdictions": {r[0]: r[1] for r in conn.execute("SELECT jurisdiction, COUNT(*) FROM documents GROUP BY 1 ORDER BY 2 DESC")},
        "pages": q("SELECT COUNT(*) FROM pages"),
        "passages": q("SELECT COUNT(*) FROM passages"),
        "governed_documents": q("SELECT COUNT(DISTINCT doc_id) FROM governance"),
        "audit_events": q("SELECT COUNT(*) FROM audit_trail"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "stats"])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--catalogue", type=Path, default=None)
    ap.add_argument("--source-collection", default="governmentpublications")
    ap.add_argument("--indexed", default="", help="collections (config/collections) to add as indexed corpora")
    args = ap.parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = build.open_registry(args.db)
    if args.command == "build":
        if args.catalogue:
            print("catalogue", build.add_catalogue(conn, build.read_catalogue(args.catalogue),
                                                    source_collection=args.source_collection))
        for name in [n for n in args.indexed.split(",") if n]:
            from archive_debugger.audit import collections
            from archive_debugger.audit.run import corpus_connection
            from archive_debugger.local_env import load_local_env
            load_local_env(log=None)
            coll = collections.load(name)
            print(name, build.add_indexed(conn, corpus_connection(coll), coll.scope))
        print("governance", build.add_governance(conn, REGISTER))
    print(json.dumps(stats(conn), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
