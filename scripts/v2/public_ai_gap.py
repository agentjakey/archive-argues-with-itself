"""The public AI gap table: proprietary and open-weight writers side by side on the same benchmark
split, per expected evidence state, from benchmark runs and the audit panel's decisions.

    python scripts/v2/public_ai_gap.py --runs val-v2-h45 val-v2-h55 val-v2-glm53 val-v2-gemma4
        --audit val-judge-1 --name validation-writers

For each run and each expected state (the benchmark label's verdict): strict SUPPORTS, ANSWERS
failures, false refusals (answerable items refused), should-refuse items refused, then overall
latency p50 / p95, cost per answer, the writer's licence and where it can run (from the candidate
entry in config/writers.toml whose model matches the run's writer). Writes
reports/v2/benchmark/scores/<name>/gap.json and gap.md. Reads files only; no model is called."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit.records import read_jsonl  # noqa: E402
from archive_debugger.generate import writers  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_benchmark", REPO / "scripts" / "v2" / "run_benchmark.py")
rb = importlib.util.module_from_spec(_spec)
sys.modules["run_benchmark"] = rb
_spec.loader.exec_module(rb)

NL = chr(10)
STATE_METRICS = ("supports_strict", "answers_failure", "false_refusal_rate", "refusal_rate_should_refuse")


def candidate_for(writer: str, candidates: dict) -> dict:
    for name, c in candidates.items():
        if c.get("model") == writer:
            return {"candidate": name, **c}
    return {"candidate": None, "licence": "not listed in config/writers.toml", "runs_on": "not listed"}


def by_state(rows: list, supports: dict, answers: dict) -> dict:
    out: dict = {}
    for r in rows:
        state = r.get("expected_verdict")
        bucket = out.setdefault(state, {m: [0, 0] for m in STATE_METRICS} | {"items": 0})
        bucket["items"] += 1
        c = rb.contributions(r, supports, answers)
        for m in STATE_METRICS:
            bucket[m][0] += c[m][0]
            bucket[m][1] += c[m][1]
    return {s: {"items": b["items"], **{m: rb.rate(b[m][0], b[m][1]) for m in STATE_METRICS}}
            for s, b in sorted(out.items(), key=lambda kv: str(kv[0]))}


def gap(runs: list, audit_runs: list, *, out_root: Path = rb.DEFAULT_OUT, audit_dir: Path = rb.DEFAULT_AUDIT_DIR,
        candidates: dict = None) -> dict:
    candidates = writers.load_candidates() if candidates is None else candidates
    decisions = rb.load_decisions(audit_runs, audit_dir)
    result = {"format": 1, "runs": {}, "audit_runs": list(audit_runs), "generated": rb.now_iso()}
    for run_id in runs:
        run_dir = Path(out_root) / "runs" / run_id
        rows = read_jsonl(run_dir / "answers.jsonl")
        judge_items = read_jsonl(run_dir / "judge_items.jsonl") if (run_dir / "judge_items.jsonl").exists() else []
        info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        supports, answers, _, _, _ = rb.panel_finals(judge_items, decisions)
        summary = rb.score_run(rows, judge_items, decisions)
        writer = (info.get("config") or {}).get("writer")
        cand = candidate_for(writer, candidates)
        result["runs"][run_id] = {
            "writer": writer, "provider": (info.get("config") or {}).get("provider", "anthropic"),
            "pipeline_label": info.get("pipeline_label"), "split": (info.get("config") or {}).get("split"),
            "licence": cand.get("licence"), "runs_on": cand.get("runs_on"), "family": cand.get("family"),
            "items": summary["items"], "answered": summary["answered"], "errors": summary["errors"],
            "overall": {m: summary["metrics"][m] for m in STATE_METRICS + ("state_accuracy", "recall_at_10")},
            "by_state": by_state(rows, supports, answers),
            "latency_s": summary["latency_s"], "cost_per_answer": summary["metrics"]["cost_per_answer"]["value"],
            "spend_usd": summary["spend_usd"], "left_to_person": summary["left_to_person"],
        }
    return result


def _v(r: dict) -> str:
    if not r or r.get("value") is None:
        return "-"
    return f"{r['value']:.3f} ({r['num']}/{r['den']})"


def _s(x, digits=1) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def gap_markdown(result: dict) -> str:
    lines = ["# Public AI gap: writers on the same split", "",
             f"Generated {result['generated']} by scripts/v2/public_ai_gap.py; audit runs "
             f"{', '.join(result['audit_runs']) or 'none'}. Same prompts and gates for every writer; temperature 0 "
             "where the endpoint takes it. SUPPORTS and ANSWERS are the audit panel's final verdicts (no judge from "
             "the writer's family). Rates are over items answered without an error.", "",
             "| Writer | Licence | Where it can run | Strict SUPPORTS | ANSWERS failures | False refusals | "
             "Should-refuse refused | State accuracy | p50 / p95 s | USD per answer | Errors |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for run_id, r in result["runs"].items():
        o = r["overall"]
        lines.append(f"| {r['writer']} | {r['licence']} | {r['runs_on']} | {_v(o['supports_strict'])} | "
                     f"{_v(o['answers_failure'])} | {_v(o['false_refusal_rate'])} | "
                     f"{_v(o['refusal_rate_should_refuse'])} | {_v(o['state_accuracy'])} | "
                     f"{_s(r['latency_s']['p50'])} / {_s(r['latency_s']['p95'])} | {_s(r['cost_per_answer'], 4)} | "
                     f"{r['errors']} |")
    states = sorted({s for r in result["runs"].values() for s in r["by_state"]}, key=str)
    for state in states:
        lines += ["", f"## Expected state: {state}", "",
                  "| Writer | Items | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for r in result["runs"].values():
            b = r["by_state"].get(state)
            if not b:
                continue
            lines.append(f"| {r['writer']} | {b['items']} | {_v(b['supports_strict'])} | {_v(b['answers_failure'])} | "
                         f"{_v(b['false_refusal_rate'])} | {_v(b['refusal_rate_should_refuse'])} |")
    return NL.join(lines) + NL


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--audit", nargs="*", default=[])
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path, default=rb.DEFAULT_OUT)
    args = p.parse_args(argv)
    result = gap(args.runs, args.audit, out_root=args.out)
    out_dir = Path(args.out) / "scores" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gap.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    with (out_dir / "gap.md").open("w", encoding="utf-8", newline=NL) as fh:
        fh.write(gap_markdown(result))
    print(gap_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
