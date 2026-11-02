"""The whole-collection build, one command per executor, on this laptop and Cloudflare.

    python scripts/v2/full_build.py --executor workers_ai --dry-run     # estimate and steps
    python scripts/v2/full_build.py --executor workers_ai               # build what is ready, then embed it
    python scripts/v2/full_build.py --executor local                    # embed on this laptop's CPU (free, slow)
    python scripts/v2/full_build.py --executor k8s --values k8s/values.toml --dry-run   # donated GPUs

Steps, for every shard in config/shards/plan.json whose text is all fetched:
  1. fetch     scripts/v2/catalogue.py fulltext (a scheduled task; shard by shard; resumes from R2)
  2. build     scripts/v2/shard_builder.py run --once: compile the fetched text into pages and passages,
               pack the shard's corpus database, its coverage file and embedding input, upload all of it
               to R2 under shards/v1/<shard>/ with checksums, then delete the local copies (heavy lock,
               4 GB free memory, 50 GB free disk)
  3. embed     scripts/v2/shard_builder.py embed --executor <executor>: the index spec's model only;
               Workers AI through the archive-argues-audit gateway, metered against the embedding cap
  4. gates     each shard's manifest read back from R2; the release gates run when shards are served
Every step resumes where it stopped. The build and the fetch normally run as scheduled tasks
(.github/workflows/build-shards.yml); this command does one pass by hand.
"""
from __future__ import annotations

import argparse
import json
import subprocess
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
}


def estimate(plan: dict, executor: str) -> dict:
    passages = plan["totals"]["est_passages"]
    docs = plan["totals"]["documents"]
    out = {"shards": plan["totals"]["shards"], "documents": docs, "est_passages": passages,
           "compile_hours_laptop": round(docs * MEASURED["compile_seconds_per_item"] / 3600, 1)}
    if executor == "local":
        out["embed_hours_laptop"] = round(passages / MEASURED["embed_passages_per_second_cpu"] / 3600, 1)
        out["cost_usd"] = 0.0
    elif executor == "workers_ai":
        got = subprocess.run([sys.executable, str(REPO / "scripts" / "v2" / "shard_builder.py"), "estimate"],
                             capture_output=True, text=True)
        out["embedding"] = json.loads(got.stdout) if got.stdout.strip().startswith("{") else got.stdout
    else:
        lo, hi = ASSUMED["embed_passages_per_second_gpu"]
        out["embed_gpu_hours"] = [round(passages / hi / 3600, 1), round(passages / lo / 3600, 1)]
        out["basis"] = "GPU rate not measured: a planning range; the first GPU unit measures it"
    return out


def steps(executor: str, values: str | None) -> list:
    embed = (f"cluster.py up --values {values} --job embed-<shard>, one per built shard" if executor == "k8s"
             else f"shard_builder.py embed --executor {executor}")
    return ["catalogue.py fulltext (scheduled task ArchiveArgues-FullTextFetch)",
            "shard_builder.py run --once (scheduled task ArchiveArgues-ShardBuilder runs it continuously)",
            embed]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--executor", choices=["local", "workers_ai", "k8s"], required=True)
    ap.add_argument("--values", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    print(json.dumps(estimate(plan, args.executor), indent=1))
    for line in steps(args.executor, args.values):
        print("  " + line)
    if args.dry_run:
        return 0
    if args.executor == "k8s":
        print("the k8s executor waits for a donated cluster: render and apply with scripts/v2/cluster.py")
        return 2
    builder = [sys.executable, str(REPO / "scripts" / "v2" / "shard_builder.py")]
    code = subprocess.run(builder + ["run", "--once"]).returncode
    if code:
        return code
    return subprocess.run(builder + ["embed", "--executor", args.executor]).returncode


if __name__ == "__main__":
    sys.exit(main())
