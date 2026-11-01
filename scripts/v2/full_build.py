"""The whole-collection build, one command per executor (Phase 4 prep). Not run yet: `--dry-run`
prints every step and the time and cost estimate; without it, the build runs.

    python scripts/v2/full_build.py --executor local --dry-run
    python scripts/v2/full_build.py --executor workers_ai --dry-run
    python scripts/v2/full_build.py --executor k8s --values k8s/values.toml --dry-run

Steps, for every shard in config/shards/plan.json:
  1. compile  the shard's fetched text into pages and passages (a compile job; CPU everywhere)
  2. pack     the shard's corpus database (the corpus builder's schema and normalizer)
  3. embed    the shard's passages (an embed job: fastembed on CPU, the Workers AI embedding model, or
              sentence-transformers on the cluster's GPUs)
  4. coverage the shard's static coverage file for the router
  5. upload   database, vectors and coverage to R2 under shards/<build>/<shard>/
Every step is a resumable job keyed by its inputs, so the command can be run again after any stop.
The full-text fetch (scripts/v2/catalogue.py fulltext) must have reached the shard's documents.

Estimates use measured rates where they exist (this laptop: compile about 1.5 s an item including
R2; embed 30 to 33 passages a second; Workers AI and GPU rates are not measured and are stated as
assumptions) and the plan's passage counts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

PLAN = REPO / "config" / "shards" / "plan.json"
MEASURED = {
    "compile_seconds_per_item": 1.5,          # bounded run: 11 units of 20 items at 15 to 16 s each
    "embed_passages_per_second_cpu": 31.0,     # bounded run: 29.0 to 32.7 on this laptop (fastembed)
}
ASSUMED = {
    "embed_passages_per_second_gpu": (1000, 5000),     # not measured: a planning range for one GPU
    "workers_ai_tokens_per_passage": 280,              # passages are about 300 words; tokens are an assumption
    "rented_cpu_cores": 32,                            # a rented CPU box; laptop rate scaled by cores/8
}


def estimate(plan: dict, executor: str) -> dict:
    from archive_debugger.audit.prices import PRICES
    passages = plan["totals"]["est_passages"]
    docs = plan["totals"]["documents"]
    compile_h = docs * MEASURED["compile_seconds_per_item"] / 3600
    out = {"shards": plan["totals"]["shards"], "documents": docs, "est_passages": passages,
           "compile_hours_one_process": round(compile_h, 1)}
    if executor == "local":
        out["embed_hours"] = round(passages / MEASURED["embed_passages_per_second_cpu"] / 3600, 1)
        out["cost_usd"] = 0.0
        out["basis"] = "measured on this laptop; it would run for weeks"
    elif executor == "workers_ai":
        price = PRICES["@cf/baai/bge-m3"]
        tokens = passages * ASSUMED["workers_ai_tokens_per_passage"]
        cores = ASSUMED["rented_cpu_cores"]
        out["embed_model"] = "@cf/baai/bge-m3 (a different index: run A's Phase 3 decides the model)"
        out["embed_cost_usd"] = round(tokens / 1e6 * price.input_per_m, 2)
        out["compile_hours_rented_box"] = round(compile_h / (cores / 8), 1)
        out["basis"] = (f"Workers AI price {price.input_per_m} USD per million tokens ({price.source}); "
                        f"{ASSUMED['workers_ai_tokens_per_passage']} tokens a passage assumed; compile on a "
                        f"{cores}-core box scaled from the laptop")
    else:
        lo, hi = ASSUMED["embed_passages_per_second_gpu"]
        out["embed_gpu_hours"] = [round(passages / hi / 3600, 1), round(passages / lo / 3600, 1)]
        out["basis"] = "GPU rate not measured: a planning range; the first GPU unit measures it"
    return out


def steps(plan: dict, executor: str, values: str | None) -> list:
    build = f"plan-{plan['target_passages']}"
    cmds = []
    for s in plan["shards"]:
        sid = s["shard_id"]
        cmds.append(f"compile  {sid}: jobs.py prepare compile-{sid} --source data/shards/{sid}.txt && "
                    + (f"cluster.py up --values {values} --job compile-{sid}" if executor == "k8s"
                       else f"jobs.py run compile-{sid} --executor local --store r2"))
        cmds.append(f"pack     {sid}: data/shards/{sid}/civic.db from the compile manifest")
        embed_exec = {"local": "local", "workers_ai": "workers_ai", "k8s": "k8s"}[executor]
        cmds.append(f"embed    {sid}: " + (f"cluster.py up --values {values} --job embed-{sid}" if executor == "k8s"
                                           else f"jobs.py run embed-{sid} --executor {embed_exec} --store r2"))
        cmds.append(f"coverage {sid}: data/shards/{sid}/coverage.json")
        cmds.append(f"upload   {sid}: R2 shards/{build}/{sid}/")
    return cmds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--executor", choices=["local", "workers_ai", "k8s"], required=True)
    ap.add_argument("--values", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    print(json.dumps(estimate(plan, args.executor), indent=1))
    todo = steps(plan, args.executor, args.values)
    print(f"{len(todo)} steps; first five:")
    for line in todo[:5]:
        print("  " + line)
    if args.dry_run:
        return 0
    print("The full build has not been approved to run: Jake decides when and where (docs/CLUSTER.md).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
