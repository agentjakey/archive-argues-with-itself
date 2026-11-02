"""AI adjudication of the judge checks an audit panel left undecided (source "adjudicated-ai").

    python scripts/v2/adjudicate_checks.py render --name test-final --audit judge-test-v1 judge-test-v2-glm53-low-dw0
    python scripts/v2/adjudicate_checks.py apply  --name test-final

render: every SUPPORTS check (sentence items) and ANSWERS check (answer items) whose panel final is empty
(the judges split, or one never answered), from each audit run's panel.jsonl and items.jsonl. The items
of all the runs are shuffled together (seed 20261105) and each gets an opaque key, so the adjudicator
cannot tell which pipeline wrote the answer: the key map stays in keys.json, never in a batch. Batches go
to reports/v2/audit/adjudicated/<name>/batchN.txt with the reference guide (prompts.REFERENCE_GUIDE);
the adjudicator writes batchN.labels.jsonl: {"key", "supports" | "answers": "pass"|"partial"|"fail",
"note"}. IN SCOPE checks are not adjudicated: no benchmark score uses them.

apply: checks every rendered check has exactly one label, then writes runs/<audit run>/adjudicated.jsonl
({item_id, check, final, note, source "adjudicated-ai", name}) for each audit run. run_benchmark.py score
reads that file beside panel.jsonl and fills the panel's empty finals with it, counting them apart."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import prompts  # noqa: E402
from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR  # noqa: E402

OUT = AUDIT_DIR / "adjudicated"
ADJUDICATED = "adjudicated-ai"
SEED = 20261105
CHECK_OF_KIND = {"sentence": "supports", "answer": "answers"}


def undecided(audit_run: str) -> list:
    """[(judge item, check)] whose final is empty in this run's panel decisions."""
    run_dir = AUDIT_DIR / "runs" / audit_run
    items = {it["item_id"]: it for it in read_jsonl(run_dir / "items.jsonl")}
    out = []
    for d in read_jsonl(run_dir / "panel.jsonl"):
        check = CHECK_OF_KIND.get(d.get("kind"))
        entry = (d.get("checks") or {}).get(check) if check else None
        if entry is not None and entry.get("final") is None and d["item_id"] in items:
            out.append((items[d["item_id"]], check))
    return out


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ast.literal_eval(value)


def render(item: dict, check: str, key: str) -> str:
    filters = item.get("filters")
    filters = filters if isinstance(filters, str) else json.dumps(filters or {})
    lines = [f"=== KEY {key}  check={check}  collection={item.get('collection')}",
             f"QUESTION: {item['question']}", f"FILTERS: {filters}"]
    if check == "answers":
        lines += [f"ANSWER: {item.get('answer_text')}", "LABEL: answers in pass|partial|fail"]
    else:
        lines += [f"WHOLE ANSWER (context): {item.get('answer_text')}",
                  f"SENTENCE TO JUDGE (no. {item.get('sentence_no')}): {item.get('sentence')}"]
        for n, c in enumerate(as_list(item.get("citations")), 1):
            lines.append(f"<page id={n} passage={c.get('passage_id')} title={c.get('title')!r} year={c.get('year')} "
                         f"jurisdiction={c.get('jurisdiction')} leaf={c.get('leaf_index')}>")
            lines.append(str(c.get("text") or "").strip())
            lines.append("</page>")
        lines.append("LABEL: supports in pass|partial|fail")
    return "\n".join(lines) + "\n"


def cmd_render(args) -> int:
    out_dir = OUT / args.name
    if (out_dir / "keys.json").exists():
        raise SystemExit(f"{out_dir} is already rendered; a new render would change the keys")
    pending = []
    for run in args.audit:
        pending += [(run, it, check) for it, check in undecided(run)]
    random.Random(SEED).shuffle(pending)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys, texts = {}, []
    for run, it, check in pending:
        key = hashlib.sha256(f"{args.name}|{run}|{it['item_id']}|{check}".encode("utf-8")).hexdigest()[:10]
        keys[key] = {"audit_run": run, "item_id": it["item_id"], "check": check}
        texts.append(render(it, check, key))
    batches = [texts[i:i + args.batch_size] for i in range(0, len(texts), args.batch_size)]
    for n, batch in enumerate(batches, 1):
        (out_dir / f"batch{n}.txt").write_text("\n".join(batch), encoding="utf-8", newline="\n")
    guide = ("# REFERENCE GUIDE (reference prompt version " + prompts.REFERENCE_PROMPT_VERSION + ")\n\n"
             + prompts.REFERENCE_GUIDE)
    (out_dir / "guide.txt").write_text(guide, encoding="utf-8", newline="\n")
    (out_dir / "keys.json").write_text(json.dumps({"name": args.name, "audit_runs": args.audit, "seed": SEED,
                                                   "keys": keys}, indent=1), encoding="utf-8")
    counts = Counter((v["audit_run"], v["check"]) for v in keys.values())
    print(f"{len(keys)} undecided checks in {len(batches)} batches under {out_dir}: {dict(counts)}")
    return 0


def cmd_apply(args) -> int:
    out_dir = OUT / args.name
    keys = json.loads((out_dir / "keys.json").read_text(encoding="utf-8"))
    labels = {}
    for path in sorted(out_dir.glob("batch*.labels.jsonl")):
        for row in read_jsonl(path):
            labels[row["key"]] = row
    missing = [k for k in keys["keys"] if k not in labels]
    bad = []
    for k, row in labels.items():
        meta = keys["keys"].get(k)
        if meta is None or row.get(meta["check"]) not in ("pass", "partial", "fail") or not str(row.get("note") or "").strip():
            bad.append(k)
    if missing or bad:
        print(f"missing {len(missing)} {missing[:8]}; unusable {len(bad)} {bad[:8]}")
        return 1
    by_run: dict = {}
    for k, meta in keys["keys"].items():
        row = labels[k]
        by_run.setdefault(meta["audit_run"], []).append(
            {"item_id": meta["item_id"], "check": meta["check"], "final": row[meta["check"]], "note": row["note"],
             "source": ADJUDICATED, "name": args.name, "guide_version": prompts.REFERENCE_PROMPT_VERSION})
    for run, rows in by_run.items():
        write_jsonl(AUDIT_DIR / "runs" / run / "adjudicated.jsonl", sorted(rows, key=lambda r: (r["item_id"], r["check"])))
        print(run, len(rows), dict(Counter((r["check"], r["final"]) for r in rows)))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render")
    p.add_argument("--name", required=True)
    p.add_argument("--audit", nargs="+", required=True)
    p.add_argument("--batch-size", type=int, default=45)
    p = sub.add_parser("apply")
    p.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    return {"render": cmd_render, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
