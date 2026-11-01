"""Plan the whole collection's engines (docs/formats/shards.md).

    python scripts/v2/shards.py plan [--target 1000000]

Reads data/registry/registry.db; writes config/shards/plan.json (committed: the plan is a decision)
and data/shards/members.tsv (every document's shard).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.shards import plan  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan"])
    ap.add_argument("--target", type=int, default=plan.DEFAULT_TARGET)
    ap.add_argument("--registry", type=Path, default=REPO / "data" / "registry" / "registry.db")
    args = ap.parse_args(argv)
    shards = plan.plan(plan.documents(sqlite3.connect(args.registry)), target=args.target)
    (REPO / "config" / "shards").mkdir(parents=True, exist_ok=True)
    (REPO / "data" / "shards").mkdir(parents=True, exist_ok=True)
    doc = plan.write_plan(shards, args.target, REPO / "config" / "shards" / "plan.json", REPO / "data" / "shards" / "members.tsv")
    print(json.dumps(doc["totals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
