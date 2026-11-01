"""Whole-collection sizing (Phase 2 Part A and the Gate 2a sizing addition), from the sample written
by scripts/v2/sample_collection.py and measured per-passage costs.

    python scripts/v2/size_collection.py --resamples 5000 --seed 20261101

Answers, with ranges:
  1. how big the whole collection is: pages, OCR bytes, passages, undated and unusable shares;
  2. what that costs on disk and in memory with today's index (per-passage costs fitted from the two
     built collections), and how long embedding would take at the measured throughput;
  3. how many passages one engine of each Cloudflare instance size can hold, and whether one engine
     per sub-collection fits (sub-collections from the items' archive.org collections);
  4. how long a snapshot restore would take for an engine at that size, scaled from production and
     staging restore times;
  5. what it costs at 1, 2 and 6 hours awake a day.
Intervals are percentile bootstrap intervals over the sampled items (95%). Writes
reports/v2/sizing/sizing.json."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
spec = importlib.util.spec_from_file_location("cost_estimate", HERE / "cost_estimate.py")
cost_estimate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost_estimate)

SIZING = REPO / "reports" / "v2" / "sizing"
# Measured on the two built collections (docs/v2/COST_BASELINE.md sections 5 and 9).
BUILT = {"pilot": {"passages": 745_893, "wake_bytes": 3_051_933_033, "anon_mib": 1_946,
                   "scanned_pages": 469_869, "mean_words_per_passage": 215.3},
         "microlog": {"passages": 1_136_827, "wake_bytes": 4_704_823_566, "anon_mib": 2_593,
                      "scanned_pages": 775_996, "mean_words_per_passage": 202.1}}
IMAGE_BYTES = 1_180_000_000
DISK_HEADROOM = 500_000_000
MEMORY_USABLE = 0.85                 # share of an instance's memory the index may use
# Snapshot restore, wake to ready, against the bytes restored.
RESTORES = {"production pilot (check_wakes.py, 2026-10-31)": (40.8, 3_051_933_033),
            "staging pilot (2026-10-30)": (10.4, 3_051_933_033),
            "staging microlog (2026-10-30)": (23.5, 4_704_823_566)}


def fitted_memory() -> tuple:
    """(base bytes, bytes per passage) through the two built collections' peak anonymous memory."""
    a, b = BUILT["pilot"], BUILT["microlog"]
    slope = (b["anon_mib"] - a["anon_mib"]) * 2**20 / (b["passages"] - a["passages"])
    return a["anon_mib"] * 2**20 - slope * a["passages"], slope


def disk_per_passage() -> tuple:
    rates = [v["wake_bytes"] / v["passages"] for v in BUILT.values()]
    return min(rates), max(rates)


def bootstrap_total(values: list, population: int, resamples: int, rng: random.Random) -> dict:
    n = len(values)
    means = sorted(statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(resamples))
    mean = statistics.fmean(values)
    return {"per_item_mean": round(mean, 2), "total": round(mean * population),
            "total95": [round(means[int(0.025 * resamples)] * population), round(means[int(0.975 * resamples)] * population)]}


def capacity(instance: str, base: float, per_passage_mem: float, per_passage_disk: float) -> int:
    vcpu, mem_gib, disk_gb = cost_estimate.INSTANCES[instance]
    by_memory = (mem_gib * 2**30 * MEMORY_USABLE - base) / per_passage_mem
    by_disk = (disk_gb * 1e9 - IMAGE_BYTES - DISK_HEADROOM) / per_passage_disk
    return int(max(0, min(by_memory, by_disk)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resamples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    rows = [json.loads(l) for l in (SIZING / "sample_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = json.loads((SIZING / "sample_summary.json").read_text(encoding="utf-8"))
    population = summary["identifiers"]
    measured = [r for r in rows if not r.get("metadata_error")]
    texts = [r for r in measured if r.get("has_djvutxt") and r.get("passages") is not None]
    # Passages as the corpus build would cut them, two ways (the public text has no page breaks):
    # by words, at the built corpora's words per passage; by scanned pages, at their passages per page.
    per_page = [v["passages"] / v["scanned_pages"] for v in BUILT.values()]
    per_words = [v["mean_words_per_passage"] for v in BUILT.values()]
    by_words = [r.get("words", 0) / statistics.fmean(per_words) if r.get("has_djvutxt") else 0 for r in measured]
    by_pages = [(r["imagecount"] or 0) * statistics.fmean(per_page) if r.get("has_djvutxt") else 0 for r in measured]
    share_usable = [(r["passage_quality"]["high"] + r["passage_quality"]["medium"]) / max(1, r["passages"])
                    for r in texts if r.get("passage_quality")]
    usable_share = sum(share_usable) / len(share_usable) if share_usable else None
    pages = [r["imagecount"] or 0 for r in measured]
    ocr_bytes = [r.get("ocr_bytes", 0) if r.get("has_djvutxt") else 0 for r in measured]

    base, mem_slope = fitted_memory()
    disk_low, disk_high = disk_per_passage()
    totals = {"pages": bootstrap_total(pages, population, args.resamples, rng),
              "ocr_bytes": bootstrap_total(ocr_bytes, population, args.resamples, rng),
              "passages_by_words": bootstrap_total(by_words, population, args.resamples, rng),
              "passages_by_pages": bootstrap_total(by_pages, population, args.resamples, rng),
              "words": bootstrap_total([r.get("words", 0) if r.get("has_djvutxt") else 0 for r in measured],
                                       population, args.resamples, rng)}
    p_low = min(totals["passages_by_words"]["total95"][0], totals["passages_by_pages"]["total95"][0])
    p_high = max(totals["passages_by_words"]["total95"][1], totals["passages_by_pages"]["total95"][1])
    out = {
        "population_items": population, "sample": len(rows), "measured": len(measured), "with_text": len(texts),
        "metadata_errors": len(rows) - len(measured), "download_errors": sum(1 for r in rows if r.get("download_error")),
        "undated_share": round(sum(1 for r in measured if r["year"] is None) / len(measured), 4),
        "no_ocr_text_share": round(sum(1 for r in measured if not r.get("has_djvutxt")) / len(measured), 4),
        "languages": dict(Counter(l for r in measured for l in r["languages"]).most_common(8)),
        "totals": totals,
        "passages_range95": [p_low, p_high],
        "passages_per_scanned_page_built": [round(x, 3) for x in per_page],
        "ocr_bytes_per_scanned_page": round(sum(ocr_bytes) / max(1, sum(r["imagecount"] or 0 for r in texts)), 1),
        "usable_passage_share": round(usable_share, 4) if usable_share is not None else None,
        "usable_note": "share of 300-word chunks of each item's whole text scoring medium or high OCR quality",
        "per_passage": {"memory_bytes": round(mem_slope), "memory_base_bytes": round(base),
                        "disk_bytes": [round(disk_low), round(disk_high)]},
        "whole_collection": {
            "disk_bytes": [round(p_low * disk_low), round(p_high * disk_high)],
            "memory_bytes_one_engine": [round(base + p_low * mem_slope), round(base + p_high * mem_slope)],
        },
    }
    throughput = json.loads((REPO / "reports" / "v2" / "baseline" / "embed_throughput.json").read_text(encoding="utf-8"))
    rate = throughput["passages_per_s"]
    out["embedding"] = {"measured_passages_per_s": rate, "machine": throughput["machine"],
                        "cpu_hours_for_whole_collection": [round(p_low / rate / 3600, 1), round(p_high / rate / 3600, 1)]}
    out["engines"] = {}
    for instance in cost_estimate.INSTANCES:
        cap = capacity(instance, base, mem_slope, disk_high)
        out["engines"][instance] = {"passages_per_engine": cap,
                                    "engines_for_whole_collection": [math.ceil(p_low / cap), math.ceil(p_high / cap)] if cap else None}
    # Sub-collections: each item's archive.org collections other than the parent.
    sub = Counter()
    for r in measured:
        for c in r.get("collections") or []:
            if c not in ("governmentpublications",):
                sub[c] += (r.get("words", 0) / statistics.fmean(per_words)) if r.get("has_djvutxt") else 0
    biggest = max(cost_estimate.INSTANCES, key=lambda i: cost_estimate.INSTANCES[i][1])
    big_cap = capacity(biggest, base, mem_slope, disk_high)
    out["sub_collections"] = [{"collection": c, "sample_passages_by_words": round(n),
                               "estimated_passages": round(n / len(measured) * population),
                               "fits_one_" + biggest: round(n / len(measured) * population) <= big_cap}
                              for c, n in sub.most_common(15)]
    rates = {k: b / s for k, (s, b) in RESTORES.items()}
    out["restore"] = {"bytes_per_s": {k: round(v) for k, v in rates.items()},
                      "seconds_for_full_engine": {i: [round(e["passages_per_engine"] * disk_high / max(rates.values()), 1),
                                                      round(e["passages_per_engine"] * disk_high / min(rates.values()), 1)]
                                                  for i, e in out["engines"].items()}}
    out["cost_per_engine_month"] = {i: {h: cost_estimate.estimate([i], h, 0.25, 0)["total_usd_per_month"] - cost_estimate.WORKERS_PAID_BASE
                                        for h in (1, 2, 6)} for i in cost_estimate.INSTANCES}
    r2_low, r2_high = out["whole_collection"]["disk_bytes"]
    out["r2_storage_usd_month"] = [round(max(0, b / 1e9 - cost_estimate.R2_INCLUDED_GB) * cost_estimate.R2_STORAGE_PER_GB_MONTH, 2)
                                   for b in (r2_low, r2_high)]
    (SIZING / "sizing.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
