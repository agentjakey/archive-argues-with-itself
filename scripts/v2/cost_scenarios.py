"""Monthly cost at 0, 100, 1,000 and 10,000 questions a month on the Cloudflare hosting (Phase 2
Part A). An ESTIMATE from published prices and measured per-answer costs, with every assumption
printed beside the result.

    python scripts/v2/cost_scenarios.py

Model: a question is either served from the stored answers (no engine, no model) or it is a miss,
which wakes the collection's engine (if asleep) and makes one model call. The hit share of visitor
questions is unknown (visitor questions are never read), so it is a range. Misses arrive in visits;
each visit keeps one engine awake for its restore time, the visit itself and the sleep-after
period. Hosting comes from scripts/v2/cost_estimate.py; the model cost per miss is the measured
median and worst case (docs/v2/COST_BASELINE.md section 3). The production model budget
(DAILY_MODEL_CALLS) caps model calls a day; misses past it get the record without an answer."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cost_estimate", HERE / "cost_estimate.py")
cost_estimate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost_estimate)

QUESTIONS = (0, 100, 1000, 10000)
HIT_SHARE = (0.0, 0.5)                 # assumed range for visitor questions
MISSES_PER_VISIT = (1.0, 3.0)          # assumed: a visit asks one to three uncached questions
VISIT_MINUTES = 5.0                    # assumed time between a visit's first and last question
SLEEP_AFTER_MINUTES = 15.0             # wrangler.jsonc, production
RESTORE_SECONDS = 40.8                 # production snapshot restore, check_wakes.py, 2026-10-31
MODEL_USD_PER_MISS = (0.0067, 0.0169)  # measured median (pilot) and worst case at max_tokens
DAILY_MODEL_CALLS = 300                # wrangler.jsonc, production
DAYS = cost_estimate.DAYS


def awake_hours_per_day(misses_per_month: float, misses_per_visit: float) -> float:
    """Awake time when visits never overlap (an upper bound: overlapping visits share a wake)."""
    visits = misses_per_month / misses_per_visit
    hours = visits * (RESTORE_SECONDS / 60 + VISIT_MINUTES + SLEEP_AFTER_MINUTES) / 60 / DAYS
    return min(24.0, hours)


def scenario(questions: int) -> dict:
    rows = []
    for hit in HIT_SHARE:
        misses = questions * (1 - hit)
        answered = min(misses, DAILY_MODEL_CALLS * DAYS)
        for per_visit in MISSES_PER_VISIT:
            awake = awake_hours_per_day(misses, per_visit)
            hosting = cost_estimate.estimate(["standard-2"], awake, 0.25, 11.7)["total_usd_per_month"]
            rows.append({"hit_share": hit, "misses_per_visit": per_visit, "misses": round(misses),
                         "model_calls": round(answered), "over_daily_budget": round(misses - answered),
                         "awake_hours_per_day": round(awake, 2), "hosting_usd": hosting,
                         "model_usd": [round(answered * m, 2) for m in MODEL_USD_PER_MISS],
                         "total_usd": [round(hosting + answered * m, 2) for m in MODEL_USD_PER_MISS]})
    totals = [t for r in rows for t in r["total_usd"]]
    return {"questions_per_month": questions, "low_usd": min(totals), "high_usd": max(totals), "rows": rows}


def main() -> int:
    out = {
        "label": "ESTIMATE from published prices and measured per-answer costs; not a bill",
        "assumptions": {"hit_share": HIT_SHARE, "misses_per_visit": MISSES_PER_VISIT, "visit_minutes": VISIT_MINUTES,
                        "sleep_after_minutes": SLEEP_AFTER_MINUTES, "restore_seconds": RESTORE_SECONDS,
                        "model_usd_per_miss": MODEL_USD_PER_MISS, "daily_model_calls": DAILY_MODEL_CALLS,
                        "layout": "split, one standard-2 engine awake per visit", "cpu_active_share": 0.25,
                        "includes": "Workers Paid $5, container memory, disk and CPU, R2 storage, model calls",
                        "excludes": "domain, D1 and Worker requests within the included amounts, snapshot storage (unpriced beta)"},
        "scenarios": [scenario(q) for q in QUESTIONS],
    }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
