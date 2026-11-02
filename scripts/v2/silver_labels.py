"""Silver labels, the review queue, and the recompute once the queue is labelled.

    python scripts/v2/silver_labels.py build   --kit-run ref-kit-1 --approval-run ref-approval-1
    python scripts/v2/silver_labels.py queue   --seed 20261105
    python scripts/v2/silver_labels.py recompute --panel-run kit2-judges

build: from the reference judges' runs, a silver row per item (docs/formats/audit.md, Silver labels):
reports/v2/audit/reference/silver_kit.jsonl and silver_approval.jsonl, plus silver_labels.jsonl in the
calibration labels format (labeler "silver") so the calibration report can read it.

queue: the review queue, at most 80 items, in the form's kit format, at
reports/v2/audit/review/queue.jsonl. Every reference disagreement on the calibration kit first, then a
seeded random 40 of the agreed kit items, then up to 20 benchmark approval items, flagged ones first.
Open it with: python scripts/v2/calibration_form.py --kit reports/v2/audit/review/queue.jsonl
(labels go to reports/v2/audit/review/labels.jsonl).

recompute: reads the queue's labels (reports/v2/audit/review/labels.jsonl, the form's format) when
there are any and writes reports/v2/audit/review/status.json and status.md: (a) the panel's error
against the adjudicated labels on the random 40, (b) the silver labels' error rate on the random 40,
the panel measured against the best labels available (adjudicated where present, otherwise silver),
and the status each check may claim. Queue labels come from AI adjudication (source "adjudicated-ai";
no human has checked them) or from the author's form; an author label wins over an adjudicated one.
Before the queue is labelled, it reports agreement with reference labels and grants nothing.
Reads files only; no model is called."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import calibration, judges, panel, prompts, silver  # noqa: E402
from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, good_judgments  # noqa: E402

REF_DIR = AUDIT_DIR / "reference"
REVIEW_DIR = AUDIT_DIR / "review"
KIT = AUDIT_DIR / "calibration" / "kit.jsonl"
APPROVAL_KIT = REPO / "reports" / "v2" / "benchmark" / "approval" / "kit.jsonl"
BENCH_RUNS = ("bench-judge-microlog", "bench-judge-pilot")


def run_judgments(run_id: str) -> dict:
    return good_judgments(AUDIT_DIR / "runs" / run_id / "judgments.jsonl")


def as_label_rows(rows: list) -> list:
    out = []
    for r in rows:
        if not any(v["silver"] for v in r["checks"].values()):
            continue
        row = {"item_id": r["item_id"], "kind": r["kind"], "labeler": "silver", "review": "reference-judges"}
        for c, v in r["checks"].items():
            if v["silver"] is not None:
                row[c] = v["silver"]
        out.append(row)
    return out


def cmd_build(args) -> int:
    cfg = judges.load_panel()
    REF_DIR.mkdir(parents=True, exist_ok=True)
    kit = read_jsonl(KIT)
    approval = read_jsonl(APPROVAL_KIT)
    kit_rows = silver.build(kit, run_judgments(args.kit_run), cfg.references)
    approval_rows = silver.build(approval, run_judgments(args.approval_run), cfg.references) if args.approval_run else []
    write_jsonl(REF_DIR / "silver_kit.jsonl", kit_rows)
    write_jsonl(REF_DIR / "silver_approval.jsonl", approval_rows)
    write_jsonl(REF_DIR / "silver_labels.jsonl", as_label_rows(kit_rows))
    summary = {"references": list(cfg.references), "kit_run": args.kit_run, "approval_run": args.approval_run,
               "reference_prompt_version": prompts.REFERENCE_PROMPT_VERSION}
    for name, rows in (("kit", kit_rows), ("approval", approval_rows)):
        per_check = {}
        for r in rows:
            for c, v in r["checks"].items():
                pc = per_check.setdefault(c, {"items": 0, "silver": 0, "disagree": 0, "missing": 0, "silver_classes": {}})
                pc["items"] += 1
                if v["silver"] is not None:
                    pc["silver"] += 1
                    pc["silver_classes"][v["silver"]] = pc["silver_classes"].get(v["silver"], 0) + 1
                elif None in v["votes"].values():
                    pc["missing"] += 1
                else:
                    pc["disagree"] += 1
        summary[name] = {"items": len(rows), "agreed_items": sum(1 for r in rows if r["agreed"]), "checks": per_check}
    (REF_DIR / "silver_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("kit", "approval")}, indent=1))
    return 0


def latest_panel_rows(runs) -> dict:
    out = {}
    for run_id in runs:
        for row in read_jsonl(AUDIT_DIR / "runs" / run_id / "panel.jsonl"):
            out[row["item_id"]] = row
    return out


def cmd_queue(args) -> int:
    kit = {it["item_id"]: it for it in read_jsonl(KIT)}
    approval = read_jsonl(APPROVAL_KIT)
    kit_rows = read_jsonl(REF_DIR / "silver_kit.jsonl")
    approval_silver = {r["item_id"]: r for r in read_jsonl(REF_DIR / "silver_approval.jsonl")}
    order, counts = silver.queue(kit_rows, approval, approval_silver, latest_panel_rows(BENCH_RUNS), args.seed)
    approval_by_id = {it["item_id"]: it for it in approval}
    position = {iid: it.get("kit_position", 0) for iid, it in kit.items()}
    sections = ["reference_disagreement", "random_agreed", "benchmark_approval_flagged", "benchmark_approval"]
    ordered = []
    for s in sections:
        ids = [i for i, sec in order if sec == s]
        if s in ("reference_disagreement", "random_agreed"):
            ids.sort(key=lambda i: position.get(i, 0))     # an answer before its sentences, as in the kit
        ordered += [(i, s) for i in ids]
    version = hashlib.sha256(("queue\n" + "\n".join(f"{i}:{s}" for i, s in ordered)).encode("utf-8")).hexdigest()[:12]
    out = []
    for n, (item_id, section) in enumerate(ordered, 1):
        row = dict(kit.get(item_id) or approval_by_id[item_id])
        row.update({"kit_position": n, "kit_batch": sections.index(section) + 1, "kit_version": version,
                    "queue_format": silver.QUEUE_FORMAT})
        out.append(row)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(REVIEW_DIR / "queue.jsonl", out)
    # The section of each item is kept beside the queue, never shown in the form.
    manifest = {"queue_version": version, "seed": args.seed, "items": len(out), "counts": counts,
                "sections": {i: s for i, s in ordered}, "max_items": silver.QUEUE_MAX,
                "random_agreed": silver.RANDOM_AGREED, "approval_max": silver.APPROVAL_MAX}
    (REVIEW_DIR / "queue.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    # Whatever the 80-item cap left out (disagreements cut to make room for the random sample, and
    # approval items that did not fit) goes to an optional second file, never silently dropped.
    queued = {i for i, _ in ordered}
    left = [kit[r["item_id"]] for r in kit_rows if not r["agreed"] and r["item_id"] not in queued]
    left += [it for it in approval if it["item_id"] not in queued
             and silver.approval_flagged(it["item_id"], approval_silver.get(it["item_id"]), None)]
    extra = []
    for n, it in enumerate(left, 1):
        row = dict(it)
        row.update({"kit_position": n, "kit_batch": 1, "kit_version": version + "-extra", "queue_format": silver.QUEUE_FORMAT})
        extra.append(row)
    write_jsonl(REVIEW_DIR / "queue_extra.jsonl", extra)
    manifest["extra_items"] = len(extra)
    (REVIEW_DIR / "queue.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(f"queue {version}: {len(out)} items {counts}; optional extra file: {len(extra)} items")
    print("open it with: python scripts/v2/calibration_form.py --kit reports/v2/audit/review/queue.jsonl")
    return 0


ADJUDICATED = "adjudicated-ai"


def label_source(row: dict) -> str:
    return row.get("source") or row.get("labeler") or "author"


def author_labels(path: Path, sources: dict = None) -> dict:
    """{check: {item_id: class}} from the queue's labels: the latest row per item, an author's row
    winning over an adjudicated one. sources, when given, gets {item_id: source}."""
    latest = {}
    for row in read_jsonl(path):
        held = latest.get(row["item_id"])
        if held is not None and label_source(held) != ADJUDICATED and label_source(row) == ADJUDICATED:
            continue
        latest[row["item_id"]] = row
    out = {c: {} for c in prompts.ALL_CHECKS}
    for item_id, row in latest.items():
        if sources is not None:
            sources[item_id] = label_source(row)
        for c in prompts.ALL_CHECKS:
            if row.get(c):
                out[c][item_id] = row[c]
    return out


def panel_finals(done: dict, items: list, cfg, override: tuple = None) -> dict:
    """{check: {item_id: final}} under the configured per-check routes, or one pair for every check."""
    out = {c: {} for c in prompts.ALL_CHECKS}
    gate = {"valid": None, "flags": []}
    for it in items:
        checks = prompts.KIND_CHECKS[prompts.kind_of(it)]
        routes = {c: ((tuple(override), cfg.escalation) if override else cfg.route(c)) for c in checks}
        names = {n for pair, esc in routes.values() for n in list(pair) + ([esc] if esc else [])}
        d = panel.decide_routes(it, gate, routes, {n: done.get((it["item_id"], n)) for n in names})
        for c, v in d["checks"].items():
            out[c][it["item_id"]] = v["final"]
    return out


def cmd_recompute(args) -> int:
    cfg = judges.load_panel()
    manifest = json.loads((REVIEW_DIR / "queue.json").read_text(encoding="utf-8"))
    sections = manifest["sections"]
    random_ids = sorted(i for i, s in sections.items() if s == "random_agreed")
    labels_path = REVIEW_DIR / "labels.jsonl"
    sources = {}
    author = author_labels(labels_path, sources)
    labelled = {i for c in author.values() for i in c}
    random_labelled = [i for i in random_ids if i in labelled]
    author_ready = len(random_labelled) == len(random_ids) and bool(random_ids)

    kit_rows = read_jsonl(REF_DIR / "silver_kit.jsonl")
    silver_l = silver.silver_labels(kit_rows)
    best = {c: {**silver_l.get(c, {}), **author.get(c, {})} for c in prompts.CHECKS}
    items = read_jsonl(AUDIT_DIR / "runs" / args.panel_run / "items.jsonl")
    done = good_judgments(AUDIT_DIR / "runs" / args.panel_run / "judgments.jsonl")
    finals = panel_finals(done, items, cfg, args.panel)
    chosen = tuple(args.panel) if args.panel else tuple(
        f"{c}: {' + '.join(cfg.route(c)[0])}" + (f" (escalation {cfg.route(c)[1]})" if cfg.route(c)[1] else "")
        for c in prompts.CHECKS)

    report = {"panel": list(chosen), "escalation": cfg.escalation, "panel_run": args.panel_run,
              "queue_version": manifest["queue_version"], "labelled_items": len(labelled),
              "label_sources": dict(sorted(Counter(sources.values()).items())),
              "random_agreed": {"items": len(random_ids), "labelled": len(random_labelled)},
              "author_ready": author_ready, "checks": {}}
    silver_err = silver.silver_error(kit_rows, author, random_labelled) if random_labelled else None
    report["silver_error_random_agreed"] = silver_err
    for c in prompts.CHECKS:
        vs_best = calibration.compare(best[c], finals[c])
        vs_silver = calibration.compare(silver_l.get(c, {}), finals[c])
        on_random = {i: author[c][i] for i in random_labelled if i in author[c]}
        vs_author_random = calibration.compare(on_random, finals[c]) if on_random else None
        report["checks"][c] = {
            "agreement_with_reference_labels": vs_silver,
            "against_best_labels": vs_best,
            "panel_error_vs_adjudicated_random_agreed": vs_author_random,
            "status": silver.status(c, vs_best["bar"], author_ready, silver_err),
        }
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEW_DIR / "status.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    def fmt(m):
        if not m or m["items_decided"] == 0:
            return "-"
        k = f"{m['kappa_binary']:.3f}" if m["kappa_binary"] is not None else "-"
        fp = m["false_pass"]
        fpr = f"{fp['rate']:.3f} (to {fp['wilson'][1]:.3f})" if fp["rate"] is not None else "-"
        return (f"n={m['items_decided']}, kappa {k}, error {m['error_rate']:.3f} (to {m['error_wilson'][1]:.3f}), "
                f"false-pass {fpr}, not-pass recall {m['not_pass_recall']['hits']}/{m['not_pass_recall']['n']}")

    lines = [f"# Audit status: panel {'; '.join(chosen)}", "",
             f"Queue {manifest['queue_version']}; labels on {len(labelled)} items (by source: "
             f"{', '.join(f'{k} {v}' for k, v in report['label_sources'].items()) or 'none'}); random agreed "
             f"sample {len(random_labelled)} of {len(random_ids)} labelled.", ""]
    if report["label_sources"].get(ADJUDICATED):
        lines += ["Labels with source adjudicated-ai come from AI adjudication: each item read against its page "
                  "and decided with a one-line reason. No human has checked them yet; outside review is planned.", ""]
    if not author_ready:
        lines += ["The review queue is not labelled yet. Everything below is agreement with reference labels "
                  "(two reference judges, silver where both agree). No check is AI-AUDITED.", ""]
    if silver_err:
        lines += [f"Silver labels' error on the random agreed sample, per item: {silver_err['item_errors']} of "
                  f"{silver_err['items']} (upper 95% bound {silver_err['wilson'][1]:.3f}; must be at most "
                  f"{silver.SILVER_ERROR_MAX})." , ""]
    lines += ["| Check | Agreement with reference labels | Against best labels | Panel vs adjudicated (random 40) | Status |",
              "| --- | --- | --- | --- | --- |"]
    for c, v in report["checks"].items():
        lines.append(f"| {c} | {fmt(v['agreement_with_reference_labels'])} | {fmt(v['against_best_labels'])} | "
                     f"{fmt(v['panel_error_vs_adjudicated_random_agreed'])} | {v['status']['status']}: {v['status']['why']} |")
    (REVIEW_DIR / "status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--kit-run", required=True)
    p.add_argument("--approval-run", default=None)
    p = sub.add_parser("queue")
    p.add_argument("--seed", type=int, required=True)
    p = sub.add_parser("recompute")
    p.add_argument("--panel-run", default="kit2-judges")
    p.add_argument("--panel", nargs=2, default=None, help="default: the panel in config/audit.toml")
    args = parser.parse_args(argv)
    return {"build": cmd_build, "queue": cmd_queue, "recompute": cmd_recompute}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
