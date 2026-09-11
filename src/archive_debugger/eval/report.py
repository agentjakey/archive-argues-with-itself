"""Compute eval metrics from human labels over the current retrieval; write
reports/phase7/eval_report.{json,md} and persist to eval_runs/eval_results.
Partial labeling produces a partial report, never an error.

Abstention: keyed on the human verdict (eval_question_gold.answerable), NOT on the
candidate qtype. No abstention-correctness RATE is reported here -- for
should-abstain questions gold is empty, so a rate is meaningless. Instead a
descriptive leakage view lists, per should-abstain question, how many surfaced
candidates the human still marked relevant (should be ~0)."""
from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from archive_debugger.eval import metrics, store
from archive_debugger.eval.label import filters_from
from archive_debugger.ingest import db

OUT_DIR = Path("reports/phase7")


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def evaluate(conn, retriever, *, recall_ks, ndcg_k, min_relevant, top_n) -> dict:
    questions = store.list_questions(conn)
    per_q = []
    agg = {f"recall@{k}": [] for k in recall_ks}
    agg[f"ndcg@{ndcg_k}"] = []
    leakage = []
    fetch = max([top_n, ndcg_k, *recall_ks])
    for q in questions:
        verdict = store.gold_verdict(conn, q["qid"])
        if verdict is None:
            continue  # unlabeled -> excluded (partial report)
        labels = store.get_labels(conn, q["qid"])
        gold_rel = dict(labels)
        gold_pos = {pid for pid, r in labels.items() if r > 0}
        ranked = [h["passage_id"] for h in retriever.search(q["text"], filters=filters_from(q), top_k=fetch)]
        row = {"qid": q["qid"], "qtype": q.get("qtype"), "answerable": verdict["answerable"]}
        for k in recall_ks:
            v = metrics.recall_at_k(ranked, gold_pos, k)
            row[f"recall@{k}"] = v
            if v is not None:
                agg[f"recall@{k}"].append(v)
        nd = metrics.ndcg_at_k(ranked, gold_rel, ndcg_k)
        row[f"ndcg@{ndcg_k}"] = nd
        if nd is not None:
            agg[f"ndcg@{ndcg_k}"].append(nd)
        # Abstention view keys on the HUMAN verdict, not qtype. For should-abstain
        # questions any relevant marks are retrieval leakage worth seeing.
        if verdict["answerable"] == 0:
            leakage.append({"qid": q["qid"], "n_surfaced": top_n, "n_marked_relevant": len(gold_pos)})
        per_q.append(row)
    aggregate = {m: _mean(v) for m, v in agg.items()}
    return {"labeled": len(per_q), "total": len(questions),
            "aggregate": aggregate, "per_question": per_q, "abstention_leakage": leakage}


def _persist(conn, report, config_json) -> None:
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    conn.execute("INSERT OR REPLACE INTO eval_runs (run_id, git_sha, config_json, ts) VALUES (?,?,?,?)",
                 (run_id, _git_sha(), config_json, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    for row in report["per_question"]:
        for metric, value in row.items():
            if metric in ("qid", "qtype", "answerable") or value is None:
                continue
            conn.execute("INSERT OR REPLACE INTO eval_results (run_id, qid, metric, value) VALUES (?,?,?,?)",
                         (run_id, row["qid"], metric, float(value)))
    conn.commit()


def run(config_path) -> dict:
    with Path(config_path).open("rb") as fh:
        cfg = tomllib.load(fh)
    ecfg = cfg.get("eval", {})
    recall_ks = list(ecfg.get("recall_ks", [5, 10, 20]))
    ndcg_k = int(ecfg.get("ndcg_k", 10))
    min_relevant = int(ecfg.get("abstention_min_relevant", 1))
    top_n = int(ecfg.get("label_top_n", 30))

    conn = db.init_db(db.resolve_db_path(config_path))
    from archive_debugger.retrieve.search import Retriever  # lazy
    retriever = Retriever(config_path)
    try:
        report = evaluate(conn, retriever, recall_ks=recall_ks, ndcg_k=ndcg_k,
                          min_relevant=min_relevant, top_n=top_n)
        _persist(conn, report, json.dumps(ecfg, ensure_ascii=False))
    finally:
        retriever.close()
        conn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Phase 7 eval report",
        "",
        f"labeled questions: {report['labeled']} / {report['total']}",
        "",
        "Pooled values: recall/nDCG denominators are the judged top-N pool, not the corpus, "
        "so these are pooled values, not absolute recall.",
        "",
        "## Aggregate (labeled questions only)",
    ]
    for m, v in report["aggregate"].items():
        lines.append(f"- {m}: {'n/a' if v is None else v}")
    if report["abstention_leakage"]:
        lines += ["", "## Abstention leakage (should-abstain questions)", "",
                  "| qid | surfaced | marked relevant |", "| --- | ---: | ---: |"]
        for r in report["abstention_leakage"]:
            lines.append(f"| {r['qid']} | {r['n_surfaced']} | {r['n_marked_relevant']} |")
    (OUT_DIR / "eval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compute eval metrics from human labels.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    args = p.parse_args(argv)
    report = run(args.config)
    print(json.dumps({"labeled": report["labeled"], "total": report["total"],
                      "aggregate": report["aggregate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
