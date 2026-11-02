"""Monthly cost estimate for serving every shard on Cloudflare Containers (config/serving.toml).

    python scripts/v2/serving_cost.py [--overlap 0.5] [--instance standard-2]

For each traffic scenario: engine wakes (questions x engines per question x (1 - overlap)), awake
hours (each wake keeps an engine up for sleep_after_minutes plus its own work), and memory, disk and
CPU at the published prices after the plan's included amounts. Every input is printed with the
result; the assumptions marked unmeasured stay so until the engines run on Containers.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def estimate(cfg: dict, plan: dict, *, overlap: float = None, instance: str = None) -> dict:
    eng, price, a = cfg["engines"], cfg["price"], cfg["assumptions"]
    kind = instance or eng["instance_type"]
    inst = cfg["instance"][kind]
    overlap = a["overlap"] if overlap is None else overlap
    shards = len(plan["shards"])
    out = {"instance": kind, "shards": shards, "sleep_after_minutes": eng["sleep_after_minutes"], "overlap": overlap,
           "assumptions": a, "scenarios": {}}
    for name, sc in cfg["scenario"].items():
        wakes = sc["questions"] * a["engines_per_question"] * (1 - overlap)
        awake_h = wakes * (eng["sleep_after_minutes"] / 60 + a["wake_cpu_vcpu_s"] / inst["vcpu"] / 3600)
        awake_h = min(awake_h, shards * 730)                       # never more than every shard always on
        mem_gib_s = max(0.0, awake_h * inst["memory_gib"] - price["included_memory_gib_h"]) * 3600
        disk_gb_s = max(0.0, awake_h * inst["disk_gb"] - price["included_disk_gb_h"]) * 3600
        cpu_s = wakes * a["wake_cpu_vcpu_s"] + sc["questions"] * a["engines_per_question"] * a["search_cpu_vcpu_s"]
        cpu_s = max(0.0, cpu_s - price["included_cpu_vcpu_min"] * 60)
        usd = {"memory": mem_gib_s * price["memory_usd_per_gib_s"], "disk": disk_gb_s * price["disk_usd_per_gb_s"],
               "cpu": cpu_s * price["cpu_usd_per_vcpu_s"]}
        out["scenarios"][name] = {"questions": sc["questions"], "wakes": round(wakes), "awake_hours": round(awake_h, 1),
                                  "usd": {k: round(v, 2) for k, v in usd.items()}, "total_usd": round(sum(usd.values()), 2)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--overlap", type=float, default=None)
    ap.add_argument("--instance", default=None)
    args = ap.parse_args(argv)
    cfg = tomllib.loads((REPO / "config" / "serving.toml").read_text(encoding="utf-8"))
    plan = json.loads((REPO / cfg["engines"]["plan"]).read_text(encoding="utf-8"))
    print(json.dumps(estimate(cfg, plan, overlap=args.overlap, instance=args.instance), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
