"""Build the v2 benchmark (Phase 2 Part C; format in docs/formats/audit.md, "Benchmark item"):
drafted items the judge panel passed, the v1 gold questions, split into dev, validation and test
by a seed, each file hashed.

    python scripts/v2/build_benchmark.py --judge-run bench-judge-1 --seed 20261103
    python scripts/v2/build_benchmark.py --judge-run bench-judge-1 --seed 20261103 --freeze

Sources:
  - drafted items (reports/v2/benchmark/drafts/<collection>.jsonl) whose panel verdicts in the judge
    run are pass on both well_formed and label_correct. An item the panel failed is left out; one
    left to the human queue is listed as pending and left out until a person decides it.
  - the v1 gold questions of every collection (eval_questions with eval_question_gold), labelled by
    the author: answerable becomes SUPPORTED, should-abstain becomes INSUFFICIENT_EVIDENCE.
Splits are drawn per (collection, category) so every split holds every category. The test split must
hold at least 100 should-refuse and 100 answerable items; the build says so when it does not.

Without --freeze the build is a candidate. --freeze refuses unless the person's approval sample
(reports/v2/benchmark/approval/labels.jsonl) covers every category and its rejection share is at most
--max-rejected, then writes config/benchmark_v2.lock.json with the hashes, which is committed: the
files themselves stay in reports/ (they carry page text)."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import collections  # noqa: E402
from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, corpus_connection, good_judgments  # noqa: E402

BENCH = AUDIT_DIR.parent / "benchmark"
LOCK = REPO / "config" / "benchmark_v2.lock.json"
SPLITS = (("test", 0.5), ("validation", 0.2), ("dev", 0.3))
TARGET = 100


def v1_gold(name: str) -> list:
    c = collections.load(name)
    conn = corpus_connection(c)
    rows = conn.execute("SELECT q.qid, q.text, q.filters_json, g.answerable FROM eval_questions q "
                        "JOIN eval_question_gold g ON g.qid = q.qid ORDER BY q.qid").fetchall()
    out = []
    for qid, text, filters_json, answerable in rows:
        refuse = not answerable
        out.append({"format": 1, "kind": "benchmark", "item_id": f"{name}:v1gold:{qid}", "collection": name,
                    "category": "v1_should_abstain" if refuse else "v1_answerable", "question": text,
                    "filters": json.loads(filters_json or "{}") or {},
                    "label": {"verdict": "INSUFFICIENT_EVIDENCE" if refuse else "SUPPORTED",
                              "behaviour": "Abstain: the v1 gold marks this question should-abstain." if refuse
                              else "Answer from the collection's pages; the v1 gold marks it answerable.",
                              "should_refuse": refuse},
                    "sources": [], "corpus_checks": [], "status": "author-reviewed", "origin": "v1 gold"})
    return out


def panel_status(items: list, run: str) -> dict:
    """{item_id: "pass" | "fail" | "pending" | "unjudged"} from the judge run's decisions."""
    path = AUDIT_DIR / "runs" / run / "panel.jsonl"
    decisions = {d["item_id"]: d for d in read_jsonl(path)}
    out = {}
    for it in items:
        d = decisions.get(it["item_id"])
        if d is None:
            out[it["item_id"]] = "unjudged"
        elif d["human_queue"]:
            out[it["item_id"]] = "pending"
        else:
            out[it["item_id"]] = "pass" if all(v["final"] == "pass" for v in d["checks"].values()) else "fail"
    return out


def split(items: list, seed: int) -> dict:
    groups: dict = {}
    for it in items:
        groups.setdefault((it["collection"], it["category"]), []).append(it)
    out = {name: [] for name, _ in SPLITS}
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda it: it["item_id"])
        random.Random(f"{seed}:{key}").shuffle(members)
        start = 0
        for n, (name, share) in enumerate(SPLITS):
            end = len(members) if n == len(SPLITS) - 1 else start + round(share * len(members))
            out[name].extend(members[start:end])
            start = end
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judge-run", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--max-rejected", type=float, default=0.10)
    args = parser.parse_args(argv)

    drafts = [it for name in collections.all_names() for it in read_jsonl(BENCH / "drafts" / f"{name}.jsonl")]
    status = panel_status(drafts, args.judge_run)
    accepted = [it for it in drafts if status[it["item_id"]] == "pass"]
    gold = [it for name in collections.all_names() for it in v1_gold(name)]
    items = accepted + gold
    splits = split(items, args.seed)
    out_dir = BENCH / "v2"
    files = {}
    for name, rows in splits.items():
        write_jsonl(out_dir / f"{name}.jsonl", rows)
        files[name] = {"items": len(rows), "sha256": sha256_file(out_dir / f"{name}.jsonl"),
                       "should_refuse": sum(1 for r in rows if r["label"]["should_refuse"]),
                       "answerable": sum(1 for r in rows if not r["label"]["should_refuse"]),
                       "by_category": dict(sorted(Counter(r["category"] for r in rows).items()))}
    test = files["test"]
    shortfalls = [f"test has {test[k]} {k.replace('_', '-')} items, under {TARGET}"
                  for k in ("should_refuse", "answerable") if test[k] < TARGET]
    manifest = {
        "benchmark": "archive-argues v2", "seed": args.seed, "judge_run": args.judge_run,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "drafted": len(drafts), "panel": dict(Counter(status.values())), "v1_gold": len(gold),
        "splits": files, "targets": {"test_should_refuse": TARGET, "test_answerable": TARGET},
        "shortfalls": shortfalls,
        "set_sha256": hashlib.sha256("".join(files[n]["sha256"] for n, _ in SPLITS).encode()).hexdigest(),
    }
    write_jsonl(BENCH / "pending_human.jsonl", [it for it in drafts if status[it["item_id"]] == "pending"])
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("drafted", "panel", "v1_gold", "shortfalls", "set_sha256")}, indent=1))
    for name in files:
        print(name, files[name]["items"], "answerable", files[name]["answerable"], "should-refuse", files[name]["should_refuse"])

    if args.freeze:
        approvals = {r["item_id"]: r for r in read_jsonl(BENCH / "approval" / "labels.jsonl")}
        cats = {it["category"] for it in accepted}
        seen = {it["category"] for it in accepted if it["item_id"] in approvals}
        rejected = sum(1 for r in approvals.values() if "fail" in (r.get("well_formed"), r.get("label_correct")))
        share = rejected / len(approvals) if approvals else 1.0
        if cats - seen or share > args.max_rejected:
            raise SystemExit(f"not frozen: approval sample misses {sorted(cats - seen)} or rejects {share:.0%}")
        LOCK.write_text(json.dumps({"frozen_at": manifest["built_at"], "set_sha256": manifest["set_sha256"],
                                    "splits": {n: {"items": f["items"], "sha256": f["sha256"]} for n, f in files.items()},
                                    "approval": {"sampled": len(approvals), "rejected": rejected}},
                                   indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"frozen: {LOCK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
