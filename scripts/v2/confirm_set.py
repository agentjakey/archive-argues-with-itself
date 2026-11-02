"""The confirmatory benchmark set confirm-1 (pre-registered in docs/evaluation/confirm1_preregistration.md).

    python scripts/v2/confirm_set.py exclusions
    python scripts/v2/confirm_set.py draft --collection pilot --cap 2.50
    python scripts/v2/confirm_set.py draft --collection microlog --cap 2.50
    python scripts/v2/confirm_set.py render --collection pilot --batch-size 40
    python scripts/v2/confirm_set.py apply
    python scripts/v2/confirm_set.py freeze

exclusions: every archive item already used by the benchmark (any draft file, kept or rejected; the dev,
validation and test splits; the v1 gold questions' gold passages), written with its sha256 to
reports/v2/benchmark/confirm1/excluded_items.json. Drafting reads it and never samples those items.

draft: the frozen benchmark's generator (audit/generator.py, version 1, same prompts, gates and drafting
model) for one collection with the pre-registered counts and seed. Every model reply is kept in a draft
cache, so a run stopped by a sleeping laptop or a network failure is resumed by the same command: it
replays what it already paid for and drafts only the rest. Output: confirm1/drafts/<collection>.jsonl and
.rejected.jsonl; item ids carry ":c1:" so they never collide with the frozen benchmark's.

render: the drafts that passed the gates, in batches for adjudication (confirm1/adjudication/<collection>-batchN.txt),
each with its question, label, quotes, corpus checks and full page text. The adjudicator writes
batchN.labels.jsonl: {"item_id", "well_formed": "pass"|"fail", "label_correct": "pass"|"fail", "note"}.

apply: reads every <collection>-batchN.labels.jsonl, checks each rendered item has exactly one label, and reports the
counts the pre-registration requires (at least 600 answerable and 150 should-refuse that pass both).

freeze: writes confirm1/test.jsonl (the passing items, status "adjudicated-ai") and the lock
config/benchmark_v2_confirm1.lock.json (sha256 of the split, of the excluded list and of the labels). The
runner reads it with --lock config/benchmark_v2_confirm1.lock.json --splits-dir
reports/v2/benchmark/confirm1 --out reports/v2/benchmark/confirm1 --split test --final."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import collections, generator, judges  # noqa: E402
from archive_debugger.audit.budget import Ledger  # noqa: E402
from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, corpus_connection  # noqa: E402

BENCH = REPO / "reports" / "v2" / "benchmark"
OUT = BENCH / "confirm1"
LOCK = REPO / "config" / "benchmark_v2_confirm1.lock.json"
SET_NAME = "confirm-1"
SEED = 20261110
ANSWERABLE = 330          # per collection
PER_TRAP = 18             # per should-refuse category, per collection
OCR_ITEMS = 0             # no poor-OCR items in this set
DRAFTER = "deepseek-v4-flash"
RUN_ID = "confirm1-draft"
NEED_ANSWERABLE = 600
NEED_SHOULD_REFUSE = 150
ADJUDICATED = "adjudicated-ai"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gold_items(name: str) -> set:
    """Archive items of every passage labelled for a v1 gold question (eval_labels, any relevance): the
    gold questions themselves carry no pages, so every page judged for them counts as used."""
    conn = corpus_connection(collections.load(name))
    rows = conn.execute("SELECT DISTINCT l.passage_id FROM eval_labels l "
                        "JOIN eval_question_gold g ON g.qid = l.qid").fetchall()
    return {str(r[0]).split("#", 1)[0] for r in rows if r[0] and "#" in str(r[0])}


def cmd_exclusions(args) -> int:
    used: set = set()
    files = sorted((BENCH / "drafts").glob("*.jsonl")) + sorted((BENCH / "v2").glob("*.jsonl"))
    for path in files:
        for row in read_jsonl(path):
            for s in row.get("sources") or []:
                if isinstance(s, str) and "#" in s:
                    used.add(s.split("#", 1)[0])
                elif isinstance(s, dict) and s.get("item_id"):
                    used.add(s["item_id"])
            src = row.get("source")
            if isinstance(src, str) and "#" in src:
                used.add(src.split("#", 1)[0])
    gold = set()
    for name in collections.all_names():
        gold |= gold_items(name)
    used |= gold
    ids = sorted(used)
    OUT.mkdir(parents=True, exist_ok=True)
    body = {"set": SET_NAME, "items": ids, "count": len(ids), "from_files": [str(p.relative_to(REPO)) for p in files],
            "v1_gold_items": len(gold), "sha256": sha256_bytes("\n".join(ids).encode("utf-8"))}
    (OUT / "excluded_items.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
    print(f"excluded archive items: {len(ids)} (v1 gold {len(gold)}); sha256 {body['sha256'][:12]}")
    return 0


def load_exclusions() -> set:
    path = OUT / "excluded_items.json"
    if not path.exists():
        raise SystemExit("run `confirm_set.py exclusions` first")
    return set(json.loads(path.read_text(encoding="utf-8"))["items"])


def cmd_draft(args) -> int:
    cfg = judges.load_panel()
    spec = cfg.specs[DRAFTER]
    ledger = Ledger(AUDIT_DIR / "ledger.jsonl")
    (OUT / "drafts").mkdir(parents=True, exist_ok=True)
    drafter = generator.Drafter(spec.model, ledger, RUN_ID, args.cap, gateway=cfg.workers_ai_gateway,
                                max_tokens=spec.max_tokens, cache_path=OUT / "draft_cache.jsonl")
    c = collections.load(args.collection)
    started = time.time()
    exclude = load_exclusions()
    answerable, per_trap = ANSWERABLE, PER_TRAP
    if args.seed_offset:
        # The pre-registered top-up: same generator and rules, the next seed, and every archive item the
        # earlier rounds of this set drew on excluded too, so no document gives a second question.
        for path in (OUT / "drafts").glob("*.jsonl"):
            for row in read_jsonl(path):
                for s in row.get("sources") or []:
                    if isinstance(s, dict) and s.get("item_id"):
                        exclude.add(s["item_id"])
                if isinstance(row.get("source"), str) and "#" in row["source"]:
                    exclude.add(row["source"].split("#", 1)[0])
        answerable = ANSWERABLE if args.answerable is None else args.answerable
        per_trap = PER_TRAP if args.per_trap is None else args.per_trap
    elif args.answerable is not None or args.per_trap is not None:
        raise SystemExit("--answerable and --per-trap are for the top-up (--seed-offset 1) only")
    items, rejected = generator.generate(corpus_connection(c), c, drafter, answerable=answerable, per_trap=per_trap,
                                         seed=SEED + args.seed_offset, exclude=exclude, ocr_items=OCR_ITEMS)
    for it in items + rejected:
        if "item_id" in it:
            it["item_id"] = it["item_id"].replace(":gen:", ":c1:" if not args.seed_offset else f":c1s{args.seed_offset}:")
            it["benchmark_set"] = SET_NAME
    suffix = "" if not args.seed_offset else f"_s{args.seed_offset}"
    write_jsonl(OUT / "drafts" / f"{args.collection}{suffix}.jsonl", items)
    write_jsonl(OUT / "drafts" / f"{args.collection}{suffix}.rejected.jsonl", rejected)
    totals = ledger.totals(RUN_ID)
    print(f"{args.collection}: kept {dict(Counter(it['category'] for it in items))}, rejected {len(rejected)}; "
          f"new calls {drafter.calls}, errors {len(drafter.errors)}; run spend ${totals.spent:.4f}; "
          f"{(time.time() - started) / 60:.1f} min")
    return 0


def drafts() -> list:
    rows = []
    for path in sorted((OUT / "drafts").glob("*.jsonl")):
        if not path.name.endswith(".rejected.jsonl"):
            rows += read_jsonl(path)
    return rows


def render_item(it: dict) -> str:
    lines = [f"=== ITEM {it['item_id']}  category={it['category']}  collection={it['collection']}",
             f"QUESTION: {it['question']}",
             f"FILTERS: {json.dumps(it.get('filters') or {})}",
             f"LABEL: {it['label']['verdict']} (should_refuse={it['label']['should_refuse']}). "
             f"Required behaviour: {it['label']['behaviour']}"]
    for key in ("answer_quote", "false_claim", "page_quote", "why_not_comparable", "topic"):
        if it.get(key):
            lines.append(f"{key.upper()}: {it[key]}")
    lines.append("CORPUS CHECKS: " + json.dumps([{k: v for k, v in ch.items()} for ch in it.get("corpus_checks") or []]))
    for n, s in enumerate(it.get("sources") or [], 1):
        lines.append(f"PAGE {n}: title={s.get('title')!r} year={s.get('year')} jurisdiction={s.get('jurisdiction')} "
                     f"passage={s.get('passage_id')} ocr_quality={s.get('ocr_quality')}")
        lines.append((s.get("text") or "").strip())
    return "\n".join(lines) + "\n"


def cmd_render(args) -> int:
    rows = [it for it in drafts() if it["collection"] == args.collection]
    adir = OUT / "adjudication"
    adir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.collection}-batch"
    if args.topup:
        # The top-up's drafts: those of this collection no batch has rendered yet.
        rendered = set()
        for ids in adir.glob(f"{args.collection}-*.ids"):
            rendered |= set(ids.read_text(encoding="utf-8").split())
        rows = [it for it in rows if it["item_id"] not in rendered]
        prefix = f"{args.collection}-topup-batch"
    if list(adir.glob(f"{prefix}*.txt")):
        raise SystemExit(f"{prefix} is already rendered")
    batches = [rows[i:i + args.batch_size] for i in range(0, len(rows), args.batch_size)]
    for n, batch in enumerate(batches, 1):
        name = f"{prefix}{n}"
        (adir / f"{name}.txt").write_text("\n".join(render_item(it) for it in batch), encoding="utf-8")
        (adir / f"{name}.ids").write_text("\n".join(it["item_id"] for it in batch) + "\n", encoding="utf-8")
    print(f"{len(rows)} drafts in {len(batches)} batches under {adir}")
    return 0


def read_labels() -> dict:
    labels: dict = {}
    for path in sorted((OUT / "adjudication").glob("*batch*.labels.jsonl")):
        for row in read_jsonl(path):
            labels[row["item_id"]] = row
    return labels


def checked(rows: list, labels: dict) -> tuple:
    missing = [it["item_id"] for it in rows if it["item_id"] not in labels]
    bad = [i for i, r in labels.items()
           if r.get("well_formed") not in ("pass", "fail") or r.get("label_correct") not in ("pass", "fail")
           or not str(r.get("note") or "").strip()]
    kept = [it for it in rows if it["item_id"] in labels and labels[it["item_id"]]["well_formed"] == "pass"
            and labels[it["item_id"]]["label_correct"] == "pass"]
    return missing, bad, kept


def cmd_apply(args) -> int:
    rows = drafts()
    labels = read_labels()
    missing, bad, kept = checked(rows, labels)
    answerable = sum(1 for it in kept if not it["label"]["should_refuse"])
    refuse = sum(1 for it in kept if it["label"]["should_refuse"])
    print(f"drafts {len(rows)}; labelled {len(labels)}; missing {len(missing)}; malformed labels {len(bad)}")
    print(f"pass both: {len(kept)} by category {dict(Counter(it['category'] for it in kept))}")
    failed = Counter(it["category"] for it in rows if it["item_id"] in labels and it not in kept)
    print(f"failed: {dict(failed)}")
    print(f"answerable {answerable} (need {NEED_ANSWERABLE}); should-refuse {refuse} (need {NEED_SHOULD_REFUSE})")
    if missing[:5] or bad[:5]:
        print("missing:", missing[:10], "malformed:", bad[:10])
    return 0 if not missing and not bad and answerable >= NEED_ANSWERABLE and refuse >= NEED_SHOULD_REFUSE else 1


def cmd_freeze(args) -> int:
    if LOCK.exists():
        raise SystemExit(f"{LOCK} exists: the set is frozen; a change means a new set")
    rows = drafts()
    labels = read_labels()
    missing, bad, kept = checked(rows, labels)
    answerable = sum(1 for it in kept if not it["label"]["should_refuse"])
    refuse = sum(1 for it in kept if it["label"]["should_refuse"])
    if missing or bad or answerable < NEED_ANSWERABLE or refuse < NEED_SHOULD_REFUSE:
        raise SystemExit("not ready: run `confirm_set.py apply` and fix what it reports")
    out = []
    for it in sorted(kept, key=lambda r: r["item_id"]):
        row = dict(it)
        row["status"] = ADJUDICATED
        row["adjudication"] = {"source": ADJUDICATED, "note": labels[it["item_id"]]["note"]}
        out.append(row)
    path = OUT / "test.jsonl"
    write_jsonl(path, out)
    split_sha = sha256_bytes(path.read_bytes())
    label_bytes = "\n".join(json.dumps(labels[i], sort_keys=True) for i in sorted(labels)).encode("utf-8")
    excluded = json.loads((OUT / "excluded_items.json").read_text(encoding="utf-8"))
    lock = {"set": SET_NAME, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "preregistration": "docs/evaluation/confirm1_preregistration.md", "seed": SEED,
            "splits": {"test": {"items": len(out), "sha256": split_sha}},
            "set_sha256": split_sha, "excluded_items_sha256": excluded["sha256"],
            "excluded_items": excluded["count"], "adjudication_labels_sha256": sha256_bytes(label_bytes),
            "counts": {"answerable": answerable, "should_refuse": refuse,
                       "by_category": dict(sorted(Counter(it["category"] for it in out).items())),
                       "drafts": len(rows), "failed_adjudication": len(rows) - len(kept)},
            "exclusions": "config/benchmark_v2_confirm1_exclusions.json",
            "rule": "frozen: nothing is added, edited or excluded; a change means a new set"}
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock["counts"]), "sha256", split_sha[:12])
    return 0


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description="The confirmatory benchmark set confirm-1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("exclusions")
    p = sub.add_parser("draft")
    p.add_argument("--collection", required=True)
    p.add_argument("--cap", type=float, required=True)
    p.add_argument("--seed-offset", type=int, default=0, help="1 for the pre-registered top-up (seed 20261111)")
    p.add_argument("--answerable", type=int, default=None, help="top-up only: answerable drafts per collection")
    p.add_argument("--per-trap", type=int, default=None, help="top-up only: drafts per should-refuse category")
    p = sub.add_parser("render")
    p.add_argument("--collection", required=True)
    p.add_argument("--batch-size", type=int, default=40)
    p.add_argument("--topup", action="store_true", help="render only the drafts no batch has rendered yet")
    sub.add_parser("apply")
    sub.add_parser("freeze")
    args = parser.parse_args(argv)
    return {"exclusions": cmd_exclusions, "draft": cmd_draft, "render": cmd_render, "apply": cmd_apply,
            "freeze": cmd_freeze}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
