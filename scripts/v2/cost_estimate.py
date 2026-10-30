"""Monthly hosting cost estimate for the engine on Cloudflare Containers, from awake time and size.

An ESTIMATE, labelled as one: it multiplies the published prices (Cloudflare Containers pricing,
checked 2026-10-29) by the hours the engine is awake. Memory and disk bill at the provisioned size
for every second the container runs; CPU bills only while active, which the script cannot know, so
it takes an explicit share of the awake time (--cpu-active, an assumption printed with the result).
A measured wake (scripts/v2/measure_staging.py) gives the per-wake time; each wake keeps the engine
up for at least the sleep-after period.

    python scripts/v2/cost_estimate.py --instance standard-3 --awake-hours 1 2 6
    python scripts/v2/cost_estimate.py --instance standard-2 --instance standard-2 --awake-hours 1 2 6   # split layout
"""
from __future__ import annotations

import argparse
import json
import sys

# Instance types (vCPU, memory GiB, disk GB), Cloudflare Containers limits page, 2026-10-29.
INSTANCES = {
    "standard-1": (0.5, 4, 8),
    "standard-2": (1, 6, 12),
    "standard-3": (2, 8, 16),
    "standard-4": (4, 12, 20),
}
# Workers Paid: price per unit after the monthly included amount.
MEMORY_PER_GIB_S = 0.0000025
MEMORY_INCLUDED_GIB_H = 25
CPU_PER_VCPU_S = 0.000020
CPU_INCLUDED_VCPU_MIN = 375
DISK_PER_GB_S = 0.00000007
DISK_INCLUDED_GB_H = 200
WORKERS_PAID_BASE = 5.00
R2_STORAGE_PER_GB_MONTH = 0.015
R2_INCLUDED_GB = 10
DAYS = 30


def estimate(instances: list[str], awake_hours_per_day: float, cpu_active: float, r2_gb: float) -> dict:
    seconds = awake_hours_per_day * 3600 * DAYS
    vcpu = sum(INSTANCES[i][0] for i in instances)
    memory = sum(INSTANCES[i][1] for i in instances)
    disk = sum(INSTANCES[i][2] for i in instances)
    memory_gib_s = memory * seconds
    disk_gb_s = disk * seconds
    cpu_s = vcpu * seconds * cpu_active
    memory_usd = max(0.0, memory_gib_s - MEMORY_INCLUDED_GIB_H * 3600) * MEMORY_PER_GIB_S
    disk_usd = max(0.0, disk_gb_s - DISK_INCLUDED_GB_H * 3600) * DISK_PER_GB_S
    cpu_usd = max(0.0, cpu_s - CPU_INCLUDED_VCPU_MIN * 60) * CPU_PER_VCPU_S
    r2_usd = max(0.0, r2_gb - R2_INCLUDED_GB) * R2_STORAGE_PER_GB_MONTH
    total = WORKERS_PAID_BASE + memory_usd + disk_usd + cpu_usd + r2_usd
    return {
        "instances": instances, "awake_hours_per_day": awake_hours_per_day,
        "memory_usd": round(memory_usd, 2), "disk_usd": round(disk_usd, 2), "cpu_usd": round(cpu_usd, 2),
        "r2_storage_usd": round(r2_usd, 2), "workers_paid_base_usd": WORKERS_PAID_BASE,
        "total_usd_per_month": round(total, 2),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--instance", action="append", choices=sorted(INSTANCES), required=True,
                        help="repeat for each container (two for the split layout)")
    parser.add_argument("--awake-hours", type=float, nargs="+", default=[1, 2, 6])
    parser.add_argument("--cpu-active", type=float, default=0.25,
                        help="ASSUMED share of awake time the CPU is busy (CPU bills only when active)")
    parser.add_argument("--r2-gb", type=float, default=11.7, help="data on R2: databases, vectors and artifacts")
    args = parser.parse_args(argv)
    rows = [estimate(args.instance, h, args.cpu_active, args.r2_gb) for h in args.awake_hours]
    print(json.dumps({"label": "ESTIMATE from published prices; not a bill",
                      "assumptions": {"days_per_month": DAYS, "cpu_active_share": args.cpu_active,
                                      "excludes": "model calls (Anthropic), domain, R2 operations within the free tier"},
                      "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
