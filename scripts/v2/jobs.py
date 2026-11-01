"""Batch jobs on any executor (docs/CLUSTER.md). One spec per job in config/jobs/.

  prepare  write a job's input units into the store (from a collection's corpus, or audit items)
  run      process the units that are not done (this worker's share): --executor local|workers_ai|k8s
  finish   write the manifest once every unit is done
  verify   check the manifest against the outputs
  status   units done and missing

    python scripts/v2/jobs.py prepare embed-sample --collection microlog --limit 4000 --shard 1000
    python scripts/v2/jobs.py run embed-sample --executor local
    python scripts/v2/jobs.py finish embed-sample && python scripts/v2/jobs.py verify embed-sample

The store is a local folder (JOBS_LOCAL_STORE, default build/jobs-store) or the private R2 bucket
(--store r2, credentials from the environment). In a Kubernetes Indexed Job each pod runs `run`
with --worker $JOB_COMPLETION_INDEX --workers <completions>.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.jobs import runner, spec as spec_mod, store as store_mod  # noqa: E402


def units_file(units: list) -> bytes:
    return "".join(json.dumps(u, sort_keys=True) + "\n" for u in units).encode("utf-8")


def corpus(collection: str):
    from archive_debugger.audit import collections
    from archive_debugger.audit.run import corpus_connection
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)
    return corpus_connection(collections.load(collection))


def prepare_embed(spec, store, args) -> list:
    from archive_debugger.jobs.embed import write_shard
    conn = corpus(args.collection)
    rows = conn.execute("SELECT passage_id, text FROM passages ORDER BY passage_id LIMIT ?", (args.limit,)).fetchall()
    units = []
    for n in range(0, len(rows), args.shard):
        uid = f"{args.collection}-{n // args.shard:05d}"
        store.put(f"{spec.input_prefix}/shards/{uid}.jsonl.gz", write_shard([dict(r) for r in rows[n:n + args.shard]]))
        units.append({"id": uid, "rows": len(rows[n:n + args.shard])})
    return units


def prepare_ocr(spec, store, args) -> list:
    """The pages with the lowest OCR confidence (body pages with text), and a lexicon from the
    collection's cleanest pages for the quality proxy."""
    from archive_debugger.jobs.ocr import build_lexicon
    conn = corpus(args.collection)
    # The corpus has no per-page OCR confidence; each passage has the build's quality score
    # (ingest.ocr.ocr_quality), so a page's quality is the mean over its passages.
    worst = conn.execute(
        "SELECT item_id, leaf_index, AVG(CAST(ocr_quality AS REAL)) AS q FROM passages "
        "WHERE ocr_quality IS NOT NULL AND LENGTH(text) > 400 GROUP BY item_id, leaf_index "
        "HAVING q >= ? ORDER BY q ASC LIMIT ?", (args.min_quality, args.limit)).fetchall()
    clean = conn.execute("SELECT text FROM passages WHERE ocr_quality IS NOT NULL "
                         "ORDER BY CAST(ocr_quality AS REAL) DESC LIMIT 20000").fetchall()
    lexicon = build_lexicon([r["text"] for r in clean])
    store.put(f"{spec.input_prefix}/lexicon.txt", "\n".join(sorted(lexicon)).encode("utf-8"))
    pages = []
    for r in worst:
        text = "\n".join(t["text"] for t in conn.execute(
            "SELECT text FROM passages WHERE item_id = ? AND leaf_index = ? ORDER BY char_start", (r["item_id"], r["leaf_index"])))
        pages.append({"page_ref": f"{r['item_id']}#{r['leaf_index']}", "item_id": r["item_id"], "leaf": int(r["leaf_index"]),
                      "old_text": text, "old_quality": r["q"]})
    units = []
    for n in range(0, len(pages), args.shard):
        uid = f"{args.collection}-worst-{n // args.shard:04d}"
        body = "".join(json.dumps(p, ensure_ascii=True) + "\n" for p in pages[n:n + args.shard])
        store.put(f"{spec.input_prefix}/pages/{uid}.jsonl", body.encode("utf-8"))
        units.append({"id": uid, "pages": len(pages[n:n + args.shard])})
    return units


def prepare_judge(spec, store, args) -> list:
    """Audit items (docs/formats/audit.md) from a JSONL file, cut into units."""
    items = [json.loads(line) for line in Path(args.items).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.sample:
        random.Random(args.seed).shuffle(items)
        items = items[: args.sample]
    units = []
    for n in range(0, len(items), args.shard):
        uid = f"items-{n // args.shard:05d}"
        body = "".join(json.dumps(it, ensure_ascii=True) + "\n" for it in items[n:n + args.shard])
        store.put(f"{spec.input_prefix}/items/{uid}.jsonl", body.encode("utf-8"))
        units.append({"id": uid, "items": len(items[n:n + args.shard])})
    return units


def prepare_compile(spec, store, args) -> list:
    from archive_debugger.jobs.compile import prepare
    return prepare(spec, store, args)


PREPARE = {"embed": prepare_embed, "ocr": prepare_ocr, "judge": prepare_judge, "compile": prepare_compile}


def make_process(spec, executor: str):
    if spec.kind == "embed":
        from archive_debugger.jobs.embed import make_process as mp
    elif spec.kind == "ocr":
        from archive_debugger.jobs.ocr import make_process as mp
    elif spec.kind == "judge":
        from archive_debugger.jobs.judge import make_process as mp
    else:
        from archive_debugger.jobs.compile import make_process as mp
    return mp(spec, executor)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare", "run", "finish", "verify", "status"])
    ap.add_argument("job")
    ap.add_argument("--store", default=os.environ.get("JOBS_STORE", "local"), choices=["local", "r2"])
    ap.add_argument("--executor", default="local", choices=list(spec_mod.EXECUTORS))
    ap.add_argument("--worker", type=int, default=int(os.environ.get("JOB_COMPLETION_INDEX", "0")))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("JOB_WORKERS", "1")))
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--shard", type=int, default=500)
    ap.add_argument("--collection", default="microlog")
    ap.add_argument("--items", default=None)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--max-units", type=int, default=None)
    ap.add_argument("--source", default=None, help="compile: the folder or store prefix of fetched OCR text")
    ap.add_argument("--min-quality", type=float, default=0.0, help="ocr: skip pages below this quality score (charts and blanks)")
    args = ap.parse_args(argv)
    spec = spec_mod.load(args.job)
    store = store_mod.open_store(args.store)
    if args.command == "prepare":
        units = PREPARE[spec.kind](spec, store, args)
        store.put(f"{spec.input_prefix}/{runner.UNITS}", units_file(units))
        print(f"{spec.name}: {len(units)} units in {store.describe()}/{spec.input_prefix}")
        return 0
    if args.command == "run":
        result = runner.run(spec, store, make_process(spec, args.executor), executor=args.executor,
                            worker=args.worker, workers=args.workers, limit=args.max_units)
        print(json.dumps(result))
        return 1 if result["failed"] else 0
    if args.command == "finish":
        manifest = runner.finish(spec, store)
        print(json.dumps({k: manifest[k] for k in ("job", "build_key", "complete", "missing")}))
        return 0 if manifest["complete"] else 1
    if args.command == "verify":
        problems = runner.verify(spec, store)
        print("\n".join(problems) if problems else "verified")
        return 1 if problems else 0
    units, fingerprint = runner.read_units(store, spec)
    prefix = spec.run_prefix(fingerprint)
    done = sum(1 for u in units if runner.unit_done(store, prefix, u["id"]))
    print(json.dumps({"job": spec.name, "units": len(units), "done": done, "run_prefix": prefix}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
