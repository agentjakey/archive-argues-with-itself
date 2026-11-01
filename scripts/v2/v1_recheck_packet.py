"""The v1 re-check packet (Phase 2 Part C): a seeded random 25 percent of the v1 judged sentences,
for a blind second judge.

    python scripts/v2/v1_recheck_packet.py --share 0.25 --seed 20261102

Writes reports/v2/benchmark/v1_recheck/kit.jsonl in the calibration kit format, so the second judge
labels it with the same form, blind to the v1 decision:

    python scripts/v2/calibration_form.py --kit reports/v2/benchmark/v1_recheck/kit.jsonl

and kit.json with how it was drawn. The v1 decisions are never in the packet; agreement with them is
computed afterwards from the labels file (scripts/v2/calibration_report.py reads the same format)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit.records import write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, build_items  # noqa: E402
from archive_debugger.audit import collections  # noqa: E402

OUT = AUDIT_DIR.parent / "benchmark" / "v1_recheck"
BATCH = 50


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--share", type=float, default=0.25)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    items, labels = build_items(collections.all_names())
    judged = sorted((it for it in items if it["kind"] == "sentence" and it["item_id"] in labels),
                    key=lambda it: it["item_id"])
    count = math.ceil(args.share * len(judged))
    chosen = random.Random(args.seed).sample(judged, count)
    rows = []
    for n, it in enumerate(chosen):
        row = dict(it)
        row.update({"kit_position": n + 1, "kit_batch": n // BATCH + 1})
        rows.append(row)
    version = hashlib.sha256(("v1recheck\n" + "\n".join(r["item_id"] for r in rows)).encode("utf-8")).hexdigest()[:12]
    for row in rows:
        row["kit_version"] = version
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "kit.jsonl", rows)
    manifest = {"kit_version": version, "seed": args.seed, "share": args.share, "judged_sentences": len(judged),
                "packet": len(rows), "by_collection": {c: sum(1 for r in rows if r["collection"] == c)
                                                       for c in sorted({r["collection"] for r in rows})},
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": "blind: the v1 decisions are not in the packet"}
    (OUT / "kit.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
