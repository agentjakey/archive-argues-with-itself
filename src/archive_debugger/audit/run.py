"""Run the audit pipeline (docs/formats/audit.md).

    python -m archive_debugger.audit.run --run-id probe-1 --answers 20 --seed 2026 --cap 2.00
    python -m archive_debugger.audit.run --run-id calib-1 --items reports/v2/audit/calibration/kit.jsonl --cap 6.00

Steps, each resumable (a stopped run is started again with the same command and only does what is
missing): build the judge items from every collection's v1 answers (or read them from --items),
run the deterministic gates, have each panel judge and each candidate judge read every item, send
the disagreements to the escalation judge, decide the panel's verdicts, and write the run report
with the spend per provider and the cost per judged item. Every paid call is checked against the
run's cap and the phase cap first (audit/budget.py).

Outputs go under reports/v2/audit/runs/<run id>/; the spend ledger is reports/v2/audit/ledger.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from archive_debugger.audit import calibration, collections, gates, items as items_mod, judges, panel, prompts
from archive_debugger.audit.budget import BudgetExceeded, Ledger
from archive_debugger.audit.records import append_jsonl, read_jsonl, write_jsonl

REPO = Path(__file__).resolve().parents[3]
AUDIT_DIR = REPO / "reports" / "v2" / "audit"


def corpus_connection(collection: collections.Collection):
    from archive_debugger import scopes
    from archive_debugger.eval.rundb import open_corpus_read_only
    return open_corpus_read_only(scopes.resolve_scope(collection.scope).db_path)


def build_items(names: list) -> tuple:
    all_items, labels = [], {}
    for name in names:
        c = collections.load(name)
        all_items.extend(items_mod.build_v1_items(c))
        labels.update(items_mod.v1_labels(c))
    return all_items, labels


def good_judgments(path: Path) -> dict:
    """{(item_id, judge): record} for judgments with verdicts under the current prompt version; the
    last record for a pair wins."""
    out = {}
    for rec in read_jsonl(path):
        if rec.get("prompt_version") == prompts.PROMPT_VERSION and rec.get("verdicts"):
            out[(rec["item_id"], rec["judge"])] = rec
    return out


def run_judge(spec: judges.JudgeSpec, pending: list, run_dir: Path, ledger: Ledger, run_id: str, cap: float,
              log=print) -> None:
    out = run_dir / "judgments.jsonl"
    if not pending:
        return
    log(f"[{spec.name}] {len(pending)} items to judge")
    if spec.provider == "anthropic" and spec.batch:
        records = judges.run_anthropic_batch(spec, pending, ledger, run_id, cap, run_dir / f"batch_{spec.name}.json", log=log)
        for rec in records:
            append_jsonl(out, rec)
    elif spec.provider == "anthropic":
        for it in pending:
            append_jsonl(out, judges.run_anthropic_direct(spec, it, ledger, run_id, cap))
    elif spec.provider == "workers-ai":
        judges.run_workers_ai_many(spec, pending, ledger, run_id, cap, on_record=lambda r: append_jsonl(out, r))
    else:
        raise ValueError(f"unknown provider {spec.provider}")


def report(run_id: str, run_dir: Path, items: list, labels: dict, gate_rows: dict, cfg: judges.PanelConfig,
           ledger: Ledger, decisions: list) -> dict:
    judgments = read_jsonl(run_dir / "judgments.jsonl")
    current = [j for j in judgments if j.get("prompt_version") == prompts.PROMPT_VERSION]
    ids = {it["item_id"] for it in items}
    by_judge: dict = {}
    for j in current:
        if j["item_id"] in ids:
            by_judge.setdefault(j["judge"], []).append(j)
    totals = ledger.totals(run_id)
    per_judge = {}
    for name, recs in sorted(by_judge.items()):
        latest = {}
        for r in recs:
            latest[r["item_id"]] = r
        good = [r for r in latest.values() if r.get("verdicts")]
        spent = sum(r["usd"] for r in recs)
        machine = {r["item_id"]: r["verdicts"]["supports"]["verdict"] for r in good}
        per_judge[name] = {
            "provider": cfg.specs[name].provider, "model": cfg.specs[name].model, "family": cfg.specs[name].family,
            "role": "panel" if name in cfg.judges else ("escalation" if name == cfg.escalation else "candidate"),
            "items_with_verdicts": len(good), "items_without": len(latest) - len(good),
            "errors": dict(Counter(r["error"] for r in latest.values() if r.get("error"))),
            "usd": round(spent, 6), "usd_per_item": round(spent / len(latest), 6) if latest else None,
            "input_tokens": sum(r["input_tokens"] for r in recs), "output_tokens": sum(r["output_tokens"] for r in recs),
            "v1_supports": calibration.compare({i: labels[i] for i in machine if i in labels}, machine),
        }
    panel_usd = sum(per_judge[n]["usd"] for n in list(cfg.judges) + [cfg.escalation] if n in per_judge)
    finals = {c: Counter((d["checks"][c]["final"] or "human") for d in decisions) for c in prompts.CHECKS}
    routes = {c: Counter(d["checks"][c]["route"] for d in decisions) for c in prompts.CHECKS}
    panel_supports = {d["item_id"]: d["checks"]["supports"]["final"] for d in decisions}
    out = {
        "run_id": run_id, "prompt_version": prompts.PROMPT_VERSION, "gate_version": gates.GATE_VERSION,
        "panel_version": panel.PANEL_VERSION, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": len(items), "answers": len({(it["collection"], it["qid"]) for it in items}),
        "by_collection": dict(Counter(it["collection"] for it in items)),
        "valid": dict(Counter(g["valid"] for g in gate_rows.values())),
        "gate_flags": dict(Counter(f for g in gate_rows.values() for f in g["flags"])),
        "panel": {"judges": list(cfg.judges), "escalation": cfg.escalation, "candidates": list(cfg.candidates)},
        "finals": {c: dict(v) for c, v in finals.items()}, "routes": {c: dict(v) for c, v in routes.items()},
        "human_queue_items": sum(1 for d in decisions if d["human_queue"]),
        "spend": {"run_usd": round(totals.spent, 6), "reserved_usd": round(totals.reserved, 6),
                  "by_provider": {k: round(v, 6) for k, v in totals.by_provider.items()},
                  "phase_usd": round(ledger.totals().spent, 6), "phase_cap_usd": ledger.phase_cap},
        "cost_per_judged_item": {
            "panel_with_escalation_usd": round(panel_usd / len(items), 6) if items else None,
            "everything_in_this_run_usd": round(totals.spent / len(items), 6) if items else None,
        },
        "judges": per_judge,
        "panel_v1_supports": calibration.compare({i: labels[i] for i in panel_supports if i in labels}, panel_supports),
    }
    return out


def write_markdown(r: dict, path: Path) -> None:
    lines = [f"# Audit run {r['run_id']}", "",
             f"Prompt {r['prompt_version']}, gates v{r['gate_version']}, panel v{r['panel_version']}, {r['generated_at']}.", "",
             f"{r['items']} items (answer sentences) from {r['answers']} answers: "
             + ", ".join(f"{k} {v}" for k, v in sorted(r["by_collection"].items())) + ".", "",
             f"VALID (gates): {r['valid']}. Gate flags: {r['gate_flags'] or 'none'}.", "",
             "## Spend", "",
             f"This run: ${r['spend']['run_usd']:.4f} ("
             + ", ".join(f"{k} ${v:.4f}" for k, v in sorted(r["spend"]["by_provider"].items())) + "). "
             f"Phase total: ${r['spend']['phase_usd']:.4f} of ${r['spend']['phase_cap_usd']:.2f}.", "",
             f"Cost per judged item, panel and escalation only: ${r['cost_per_judged_item']['panel_with_escalation_usd']:.5f}; "
             f"everything in this run, candidates included: ${r['cost_per_judged_item']['everything_in_this_run_usd']:.5f}.", "",
             "| Judge | Role | Family | Items with verdicts | Without | Errors | USD | USD per item | Tokens in / out |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, j in r["judges"].items():
        lines.append(f"| {name} | {j['role']} | {j['family']} | {j['items_with_verdicts']} | {j['items_without']} | "
                     f"{j['errors'] or ''} | {j['usd']:.4f} | {j['usd_per_item'] or 0:.5f} | {j['input_tokens']} / {j['output_tokens']} |")
    lines += ["", "## Panel verdicts", "", "| Check | Final verdicts | Routes |", "| --- | --- | --- |"]
    for c in prompts.CHECKS:
        lines.append(f"| {c} | {r['finals'][c]} | {r['routes'][c]} |")
    lines += ["", f"Items with at least one check in the human queue: {r['human_queue_items']}.", "",
              "## Agreement with the v1 SUPPORTS labels", "",
              "The v1 labels were proposed by a model of the same family as the Claude judge, then reviewed and "
              "decided by the author, so they may lean toward that judge. They cover SUPPORTS only. This is a first "
              "look, not calibration: calibration uses the new blind labels.", "",
              "| Judge | Decided | Exact agreement | Kappa (pass / not pass) | False passes | Missed failures |",
              "| --- | --- | --- | --- | --- | --- |"]
    rows = list(r["judges"].items()) + [("PANEL", {"v1_supports": r["panel_v1_supports"]})]
    for name, j in rows:
        m = j["v1_supports"]
        ea = f"{m['exact_agreement']:.3f}" if m["exact_agreement"] is not None else "-"
        kb = f"{m['kappa_binary']:.3f}" if m["kappa_binary"] is not None else "-"
        fp, mf = m["false_pass"], m["missed_failures"]
        lines.append(f"| {name} | {m['items_decided']} | {ea} | {kb} | {fp['count']} of {fp['of_machine_passes']} passes | "
                     f"{mf['count']} of {mf['of_human_not_pass']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cap", type=float, required=True, help="this run's spending cap in US dollars")
    parser.add_argument("--collections", nargs="*", default=None, help="default: every config/collections/*.toml")
    parser.add_argument("--answers", type=int, default=None, help="judge every sentence of this many answers")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--items", type=Path, default=None, help="judge these items (a judge_items JSONL file)")
    parser.add_argument("--judges", nargs="*", default=None, help="default: the panel and the candidates")
    parser.add_argument("--no-escalation", action="store_true")
    args = parser.parse_args(argv)

    run_dir = AUDIT_DIR / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(AUDIT_DIR / "ledger.jsonl")
    cfg = judges.load_panel()
    names = args.collections or collections.all_names()
    all_items, labels = build_items(names)
    items_path = run_dir / "items.jsonl"
    if items_path.exists():
        items = read_jsonl(items_path)
    elif args.items:
        wanted = [r["item_id"] for r in read_jsonl(args.items)]
        index = {it["item_id"]: it for it in all_items}
        items = [index[i] for i in wanted if i in index]
    elif args.answers:
        items = items_mod.select_answers(all_items, args.answers, args.seed)
    else:
        items = all_items
    write_jsonl(items_path, items)
    print(f"{len(items)} items from {len({(i['collection'], i['qid']) for i in items})} answers")

    gate_path = run_dir / "gates.jsonl"
    gate_rows = {g["item_id"]: g for g in read_jsonl(gate_path)}
    if set(gate_rows) != {it["item_id"] for it in items}:
        conns = {}
        gate_rows = {}
        for it in items:
            c = collections.load(it["collection"])
            conn = conns.setdefault(c.name, corpus_connection(c))
            gate_rows[it["item_id"]] = gates.run_gates(conn, it)
        write_jsonl(gate_path, gate_rows.values())

    judge_names = args.judges or (list(cfg.judges) + list(cfg.candidates))
    try:
        for name in judge_names:
            done = good_judgments(run_dir / "judgments.jsonl")
            pending = [it for it in items if (it["item_id"], name) not in done]
            run_judge(cfg.specs[name], pending, run_dir, ledger, args.run_id, args.cap)
        if not args.no_escalation:
            done = good_judgments(run_dir / "judgments.jsonl")
            a, b = cfg.judges
            pending = [it for it in items
                       if panel.needs_escalation(done.get((it["item_id"], a)), done.get((it["item_id"], b)))
                       and (it["item_id"], cfg.escalation) not in done]
            run_judge(cfg.specs[cfg.escalation], pending, run_dir, ledger, args.run_id, args.cap)
    except BudgetExceeded as exc:
        print(f"STOPPED before a call that could cross a cap: {exc}", file=sys.stderr)

    done = good_judgments(run_dir / "judgments.jsonl")
    decisions = [panel.decide(it["item_id"], gate_rows[it["item_id"]], cfg.judges,
                              {n: done.get((it["item_id"], n)) for n in cfg.judges},
                              done.get((it["item_id"], cfg.escalation))) for it in items]
    write_jsonl(run_dir / "panel.jsonl", decisions)
    write_jsonl(run_dir / "human_queue.jsonl", [d for d in decisions if d["human_queue"]])
    r = report(args.run_id, run_dir, items, labels, gate_rows, cfg, ledger, decisions)
    (run_dir / "report.json").write_text(json.dumps(r, indent=1, sort_keys=True), encoding="utf-8")
    write_markdown(r, run_dir / "report.md")
    print(f"spend this run ${r['spend']['run_usd']:.4f} {r['spend']['by_provider']}; phase ${r['spend']['phase_usd']:.4f}")
    print(f"report: {run_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
