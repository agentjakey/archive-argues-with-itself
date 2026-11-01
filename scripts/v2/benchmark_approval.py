"""The approval sample: drafted benchmark items the panel passed, for a person to check before the
benchmark is frozen (Phase 2 Part B.5, "a person approves a sample").

    python scripts/v2/benchmark_approval.py --judge-run bench-judge-1 --share 0.1 --seed 20261104
    python scripts/v2/calibration_form.py --kit reports/v2/benchmark/approval/kit.jsonl

A seeded share of each category (at least --minimum per category), in the calibration kit format,
labelled with the same form on two checks: well formed and label correct. The labels go to
reports/v2/benchmark/approval/labels.jsonl, which build_benchmark.py --freeze reads."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_benchmark", HERE / "build_benchmark.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

from archive_debugger.audit import collections  # noqa: E402
from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402

OUT = build.BENCH / "approval"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judge-run", required=True)
    parser.add_argument("--share", type=float, default=0.10)
    parser.add_argument("--minimum", type=int, default=3)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    drafts = [it for name in collections.all_names() for it in read_jsonl(build.BENCH / "drafts" / f"{name}.jsonl")]
    status = build.panel_status(drafts, args.judge_run)
    accepted = [it for it in drafts if status[it["item_id"]] == "pass"]
    by_category: dict = {}
    for it in accepted:
        by_category.setdefault(it["category"], []).append(it)
    rng = random.Random(args.seed)
    chosen = []
    for category in sorted(by_category):
        members = sorted(by_category[category], key=lambda it: it["item_id"])
        count = min(len(members), max(args.minimum, math.ceil(args.share * len(members))))
        chosen.extend(rng.sample(members, count))
    rng.shuffle(chosen)
    version = hashlib.sha256(("approval\n" + "\n".join(it["item_id"] for it in chosen)).encode()).hexdigest()[:12]
    rows = [dict(it, kit_position=n + 1, kit_batch=n // 50 + 1, kit_version=version) for n, it in enumerate(chosen)]
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "kit.jsonl", rows)
    summary = {"kit_version": version, "seed": args.seed, "items": len(rows),
               "by_category": {c: sum(1 for r in rows if r["category"] == c) for c in sorted(by_category)}}
    (OUT / "kit.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
