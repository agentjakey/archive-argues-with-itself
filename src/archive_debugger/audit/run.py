"""Run the audit pipeline (docs/formats/audit.md).

    python -m archive_debugger.audit.run --run-id probe-1 --answers 20 --seed 2026 --cap 2.00
    python -m archive_debugger.audit.run --run-id calib-1 --items reports/v2/audit/calibration/kit.jsonl --cap 5.00

Steps, each resumable (a stopped run is started again with the same command and only does what is
missing): build the judge items from every collection's v1 answers (sentence items and one answer
item per answer, or read them from --items), run the deterministic gates, have each panel judge and
each candidate judge read every item, send the disagreements to the escalation judge, decide the
panel's verdicts, have the escalation judge re-read a random share of the agreed passes (the
leniency review), and write the run report with the spend per provider and the cost per judged
sentence. Every paid call is checked against the run's cap and the phase cap first
(audit/budget.py). A panel that includes the model that wrote the answers is refused.

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
        if rec.get("prompt_version") == prompts.version_for(rec.get("kind") or "sentence") and rec.get("verdicts"):
            out[(rec["item_id"], rec["judge"])] = rec
    return out


BATCH_CHUNK = 60    # items per Anthropic batch, so one batch's worst case stays well under a run cap


def run_batches(spec: judges.JudgeSpec, pending: list, run_dir: Path, ledger: Ledger, run_id: str, cap: float,
                log=print, chunk: int = BATCH_CHUNK, batch_runner=None) -> None:
    """Judge `pending` in Anthropic batches of at most `chunk` items. A batch already submitted by a
    stopped run (its state file still holds a batch id) is collected first, so nothing is sent twice;
    then the rest go in new batches, each reserved and collected before the next is sent."""
    batch_runner = batch_runner or judges.run_anthropic_batch
    out = run_dir / "judgments.jsonl"
    by_id = {it["item_id"]: it for it in pending}
    for state_path in sorted(run_dir.glob(f"batch_{spec.name}*.json")):
        if judges.BatchState(state_path).load().get("batch_id"):
            for rec in batch_runner(spec, list(by_id.values()), ledger, run_id, cap, state_path, log=log):
                append_jsonl(out, rec)
                by_id.pop(rec["item_id"], None)
    rest = list(by_id.values())
    for start in range(0, len(rest), chunk):
        part = rest[start:start + chunk]
        state_path = run_dir / f"batch_{spec.name}_{int(time.time() * 1000)}.json"
        for rec in batch_runner(spec, part, ledger, run_id, cap, state_path, log=log):
            append_jsonl(out, rec)
        state_path.unlink(missing_ok=True)


def run_judge(spec: judges.JudgeSpec, pending: list, run_dir: Path, ledger: Ledger, run_id: str, cap: float,
              log=print, gateway=None) -> None:
    out = run_dir / "judgments.jsonl"
    if not pending:
        return
    log(f"[{spec.name}] {len(pending)} items to judge")
    if spec.provider == "anthropic" and spec.batch:
        run_batches(spec, pending, run_dir, ledger, run_id, cap, log=log)
    elif spec.provider == "anthropic":
        for it in pending:
            append_jsonl(out, judges.run_anthropic_direct(spec, it, ledger, run_id, cap))
    elif spec.provider == "workers-ai":
        judges.run_workers_ai_many(spec, pending, ledger, run_id, cap, on_record=lambda r: append_jsonl(out, r),
                                   gateway=gateway)
    else:
        raise ValueError(f"unknown provider {spec.provider}")


def check_items(items: list, check: str) -> list:
    return [it for it in items if check in prompts.KIND_CHECKS[prompts.kind_of(it)]]


def report(run_id: str, run_dir: Path, items: list, labels: dict, gate_rows: dict, cfg: judges.PanelConfig,
           ledger: Ledger, decisions: list, lenient: dict, review_ids: list) -> dict:
    judgments = read_jsonl(run_dir / "judgments.jsonl")
    current = [j for j in judgments if j.get("prompt_version") == prompts.version_for(j.get("kind") or "sentence")]
    ids = {it["item_id"] for it in items}
    sentences = [it for it in items if prompts.kind_of(it) == "sentence"]
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
        machine = {r["item_id"]: r["verdicts"]["supports"]["verdict"] for r in good if "supports" in r["verdicts"]}
        spec = cfg.specs[name]
        per_judge[name] = {
            "provider": spec.provider, "model": spec.model, "family": spec.family,
            "role": "panel" if name in cfg.judges else ("escalation" if name == cfg.escalation else "candidate"),
            "items_with_verdicts": len(good), "items_without": len(latest) - len(good),
            "by_kind": dict(Counter(r.get("kind", "sentence") for r in latest.values())),
            "errors": dict(Counter(r["error"] for r in latest.values() if r.get("error"))),
            "cached": sum(1 for r in recs if r.get("cached")),
            "usd": round(spent, 6),
            "usd_per_judged_sentence": round(spent / len(sentences), 6) if sentences and latest else None,
            "input_tokens": sum(r["input_tokens"] for r in recs), "output_tokens": sum(r["output_tokens"] for r in recs),
            "v1_supports": calibration.compare({i: labels[i] for i in machine if i in labels}, machine),
        }
    panel_usd = sum(per_judge[n]["usd"] for n in list(cfg.judges) + [cfg.escalation] if n in per_judge)
    by_id = {d["item_id"]: d for d in decisions}
    finals, routes = {}, {}
    for c in [c for c in prompts.ALL_CHECKS if check_items(items, c)]:
        ds = [by_id[it["item_id"]] for it in check_items(items, c)]
        finals[c] = dict(Counter((d["checks"][c]["final"] or "human") for d in ds))
        routes[c] = dict(Counter(d["checks"][c]["route"] for d in ds))
    panel_supports = {d["item_id"]: d["checks"]["supports"]["final"] for d in decisions if "supports" in d["checks"]}
    return {
        "run_id": run_id, "prompt_version": prompts.PROMPT_VERSION,
        "benchmark_prompt_version": prompts.BENCHMARK_PROMPT_VERSION, "gate_version": gates.GATE_VERSION,
        "panel_version": panel.PANEL_VERSION, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": len(items), "sentence_items": len(sentences),
        "answer_items": sum(1 for it in items if prompts.kind_of(it) == "answer"),
        "benchmark_items": sum(1 for it in items if prompts.kind_of(it) == "benchmark"),
        "answers": len({(it["collection"], it["qid"]) for it in items}),
        "by_collection": dict(Counter(it["collection"] for it in items)),
        "valid": dict(Counter(gate_rows[it["item_id"]]["valid"] for it in sentences)),
        "gate_flags": dict(Counter(f for g in gate_rows.values() for f in g["flags"])),
        "panel": {"judges": list(cfg.judges), "escalation": cfg.escalation, "candidates": list(cfg.candidates),
                  "workers_ai_gateway": cfg.workers_ai_gateway},
        "finals": finals, "routes": routes,
        "human_queue_items": sum(1 for d in decisions if d["human_queue"]),
        "leniency_review": {"share": cfg.review_share, "flag_above": cfg.lenient_above, "items": len(review_ids),
                            "checks": lenient,
                            "too_lenient": sorted(c for c, v in lenient.items() if v["too_lenient"])},
        "spend": {"run_usd": round(totals.spent, 6), "reserved_usd": round(totals.reserved, 6),
                  "by_provider": {k: round(v, 6) for k, v in totals.by_provider.items()},
                  "phase_usd": round(ledger.totals().spent, 6), "phase_cap_usd": ledger.phase_cap},
        "cost_per_judged_sentence": {
            "panel_with_escalation_usd": round(panel_usd / len(sentences), 6) if sentences else None,
            "everything_in_this_run_usd": round(totals.spent / len(sentences), 6) if sentences else None,
            "note": "per sentence item; the cost of the answer items (ANSWERS) is spread over the sentences",
        },
        "judges": per_judge,
        "panel_v1_supports": calibration.compare({i: labels[i] for i in panel_supports if i in labels}, panel_supports),
    }


def write_markdown(r: dict, path: Path) -> None:
    cost = r["cost_per_judged_sentence"]
    lines = [f"# Audit run {r['run_id']}", "",
             f"Prompt {r['prompt_version']}, gates v{r['gate_version']}, panel v{r['panel_version']}, {r['generated_at']}.", "",
             f"{r['sentence_items']} sentence items, {r['answer_items']} answer items and {r['benchmark_items']} benchmark "
             f"items from {r['answers']} answers or questions: "
             + ", ".join(f"{k} {v}" for k, v in sorted(r["by_collection"].items())) + ".", "",
             f"VALID (gates, sentences): {r['valid']}. Gate flags: {r['gate_flags'] or 'none'}.", "",
             f"Panel: {', '.join(r['panel']['judges'])}; escalation {r['panel']['escalation']}; candidates "
             f"{', '.join(r['panel']['candidates']) or 'none'}. Workers AI gateway: {r['panel']['workers_ai_gateway'] or 'none (direct)'}.", "",
             "## Spend", "",
             f"This run: ${r['spend']['run_usd']:.4f} ("
             + ", ".join(f"{k} ${v:.4f}" for k, v in sorted(r["spend"]["by_provider"].items())) + "). "
             f"Phase total: ${r['spend']['phase_usd']:.4f} of ${r['spend']['phase_cap_usd']:.2f}.", ""]
    if cost["panel_with_escalation_usd"] is not None:
        lines += [f"Cost per judged sentence, panel and escalation only: ${cost['panel_with_escalation_usd']:.5f}; "
                  f"everything in this run: ${cost['everything_in_this_run_usd']:.5f} ({cost['note']}).", ""]
    lines += ["| Judge | Role | Family | Items with verdicts | Without | Errors | Gateway cache hits | USD | USD per sentence | Tokens in / out |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, j in r["judges"].items():
        lines.append(f"| {name} | {j['role']} | {j['family']} | {j['items_with_verdicts']} | {j['items_without']} | "
                     f"{j['errors'] or ''} | {j['cached']} | {j['usd']:.4f} | {j['usd_per_judged_sentence'] or 0:.5f} | "
                     f"{j['input_tokens']} / {j['output_tokens']} |")
    lines += ["", "## Panel verdicts", "", "| Check | Final verdicts | Routes |", "| --- | --- | --- |"]
    for c in r["finals"]:
        lines.append(f"| {c} | {r['finals'][c]} | {r['routes'][c]} |")
    lr = r["leniency_review"]
    lines += ["", f"Items with at least one check in the human queue: {r['human_queue_items']}.", "",
              "## Leniency review", "",
              f"The escalation judge re-read {lr['items']} items with agreed passes ({lr['share']:.0%} of them). A check "
              f"is flagged when it did not pass more than {lr['flag_above']:.0%} of the reviewed agreed passes.", "",
              "| Check | Reviewed | Escalation did not pass | Rate (95% interval) | Flag |", "| --- | --- | --- | --- | --- |"]
    for c, v in sorted(lr["checks"].items()):
        rate = f"{v['rate']:.3f} ({v['wilson'][0]:.3f} to {v['wilson'][1]:.3f})" if v["rate"] is not None else "-"
        lines.append(f"| {c} | {v['reviewed']} | {v['disagree']} | {rate} | {'TOO LENIENT' if v['too_lenient'] else ''} |")
    lines += ["", "## Agreement with the v1 SUPPORTS labels", "",
              "The v1 labels were proposed by a model of the same family as the Claude judges, then reviewed and "
              "decided by the author, so they may lean toward those judges. They cover SUPPORTS only. This is a first "
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
    parser.add_argument("--answers", type=int, default=None, help="judge every sentence and the answer item of this many answers")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--items", type=Path, default=None, help="judge these items (a judge_items or kit JSONL file)")
    parser.add_argument("--judges", nargs="*", default=None,
                        help="judges that read every item; default: the panel and the candidates")
    parser.add_argument("--no-escalation", action="store_true")
    parser.add_argument("--no-review", action="store_true", help="skip the leniency review")
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
        rows = read_jsonl(args.items)
        index = {it["item_id"]: it for it in all_items}
        # Items that are not v1 answers (drafted benchmark items) are read whole from the file.
        index.update({r["item_id"]: r for r in rows if r.get("kind") == "benchmark"})
        wanted = [r["item_id"] for r in rows]
        missing = [i for i in wanted if i not in index]
        if missing:
            raise SystemExit(f"{len(missing)} items in {args.items} are not in the collections, e.g. {missing[:3]}")
        items = [index[i] for i in wanted]
    elif args.answers:
        items = items_mod.select_answers(all_items, args.answers, args.seed)
    else:
        items = all_items
    conflicts = judges.writer_conflicts(cfg, items)
    if conflicts:
        raise SystemExit(f"refused: panel or escalation judges {conflicts} use the model that wrote these answers; "
                         "change [panel] in config/audit.toml")
    write_jsonl(items_path, items)
    kinds = Counter(prompts.kind_of(it) for it in items)
    print(", ".join(f"{n} {kind} items" for kind, n in sorted(kinds.items())))

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

    judgments_path = run_dir / "judgments.jsonl"
    judge_names = args.judges or (list(cfg.judges) + list(cfg.candidates))

    def judge(name: str, pending: list) -> None:
        run_judge(cfg.specs[name], pending, run_dir, ledger, args.run_id, args.cap, gateway=cfg.workers_ai_gateway)

    def decide_all() -> list:
        done = good_judgments(judgments_path)
        return [panel.decide(it, gate_rows[it["item_id"]], cfg.judges,
                             {n: done.get((it["item_id"], n)) for n in cfg.judges},
                             done.get((it["item_id"], cfg.escalation))) for it in items]

    review_ids: list = []
    try:
        for name in judge_names:
            done = good_judgments(judgments_path)
            judge(name, [it for it in items if (it["item_id"], name) not in done])
        if not args.no_escalation:
            done = good_judgments(judgments_path)
            a, b = cfg.judges
            judge(cfg.escalation, [it for it in items
                                   if panel.needs_escalation(done.get((it["item_id"], a)), done.get((it["item_id"], b)),
                                                             prompts.KIND_CHECKS[prompts.kind_of(it)])
                                   and (it["item_id"], cfg.escalation) not in done])
        if not args.no_review:
            # The sample is drawn from the panel's agreed passes before the review, seeded by the run id.
            review_ids = panel.review_sample(decide_all(), cfg.review_share, args.run_id)
            done = good_judgments(judgments_path)
            wanted = set(review_ids)
            judge(cfg.escalation, [it for it in items if it["item_id"] in wanted and (it["item_id"], cfg.escalation) not in done])
    except BudgetExceeded as exc:
        print(f"STOPPED before a call that could cross a cap: {exc}", file=sys.stderr)

    decisions = decide_all()
    done = good_judgments(judgments_path)
    reviews = {i: done.get((i, cfg.escalation)) for i in review_ids}
    lenient = panel.leniency([d for d in decisions if d["item_id"] in reviews], reviews, cfg.lenient_above)
    write_jsonl(run_dir / "panel.jsonl", decisions)
    write_jsonl(run_dir / "human_queue.jsonl", [d for d in decisions if d["human_queue"]])
    r = report(args.run_id, run_dir, items, labels, gate_rows, cfg, ledger, decisions, lenient, review_ids)
    (run_dir / "report.json").write_text(json.dumps(r, indent=1, sort_keys=True), encoding="utf-8")
    write_markdown(r, run_dir / "report.md")
    print(f"spend this run ${r['spend']['run_usd']:.4f} {r['spend']['by_provider']}; phase ${r['spend']['phase_usd']:.4f}")
    if r["leniency_review"]["too_lenient"]:
        print(f"FLAG: the panel looks too lenient on {r['leniency_review']['too_lenient']}")
    print(f"report: {run_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
