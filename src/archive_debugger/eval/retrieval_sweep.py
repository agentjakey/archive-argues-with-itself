"""Phase 13 retrieval-quality sweep: the full Phase 7 eval (recall@k, nDCG@10, plus
unjudged@10/@20) on the current retriever under each switch state, persisted as
one eval_runs row per state, plus the no-model abstention sweep on the baseline
and the all-on states. Writes reports/phase13/retrieval_report.md.

States: baseline (all off), each switch alone (cap at 3 and at 5 separately;
later_years is a recorded no-op for ranking), all on with cap 3, all on with cap 5.

Pooled-labels caveat, printed in the report: gold was labeled from the BASELINE
retriever's top-30, so a ranking that surfaces new passages cannot be credited for
them; unjudged@k says how much of each top-k the labels cannot see."""
from __future__ import annotations

import argparse
import json
import tomllib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from archive_debugger.eval import report
from archive_debugger.generate import cli as gen_cli
from archive_debugger.ingest import db
from archive_debugger.retrieve.config import load_retrieve_config
from archive_debugger.retrieve.embed import make_embedder
from archive_debugger.retrieve.search import Retriever

OUT_DIR = Path("reports/phase13")
_ALL = {"section_demote": True, "fts_drop_stopwords": True, "doc_type_family_filter": True, "later_years_flag": True}
STATES: list[tuple[str, dict]] = [
    ("baseline", {}),
    ("section_demote", {"section_demote": True}),
    ("fts_drop_stopwords", {"fts_drop_stopwords": True}),
    ("doc_type_family_filter", {"doc_type_family_filter": True}),
    ("cap3", {"per_item_cap": 3}),
    ("cap5", {"per_item_cap": 5}),
    ("later_years", {"later_years_flag": True}),          # annotation only; ranking identical to baseline
    ("all_on_cap3", {**_ALL, "per_item_cap": 3}),
    ("all_on_cap5", {**_ALL, "per_item_cap": 5}),
]
SWEEP_STATES = ("baseline", "all_on_cap3", "all_on_cap5")


def run(config_path: Path, *, seed_path: Path = Path("eval/seed_questions.jsonl"), out_dir: Path = OUT_DIR,
        embedder=None, conn=None, states: Optional[list] = None) -> dict:
    with Path(config_path).open("rb") as fh:
        cfg_all = tomllib.load(fh)
    ecfg = cfg_all.get("eval", {})
    recall_ks = list(ecfg.get("recall_ks", [5, 10, 20]))
    ndcg_k = int(ecfg.get("ndcg_k", 10))
    top_n = int(ecfg.get("label_top_n", 30))
    base = load_retrieve_config(config_path)
    own_conn = conn is None
    if own_conn:
        db_path = db.resolve_db_path(config_path)
        if not Path(db_path).exists():
            raise FileNotFoundError(f"civic.db not found at {db_path}; set CIVIC_DB_PATH or fix [index].db_path")
        conn = db.init_db(db_path)     # writes eval_runs / eval_results only
    embedder = embedder or make_embedder(base.embedder, base.embedding_model, base.embedding_dim)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    section_rows = conn.execute("SELECT COUNT(section_class) FROM pages").fetchone()[0]
    out: dict = {"ts": ts, "states": {}, "sweeps": {}, "run_ids": {}}
    try:
        for name, over in (states or STATES):
            cfg = replace(base, **over)
            if cfg.section_demote and section_rows == 0:
                raise RuntimeError("pages.section_class is empty: run `python -m archive_debugger.ingest.sections` first")
            r = Retriever(None, cfg=cfg, embedder=embedder)
            try:
                rep = report.evaluate(conn, r, recall_ks=recall_ks, ndcg_k=ndcg_k,
                                      min_relevant=int(ecfg.get("abstention_min_relevant", 1)), top_n=top_n)
                run_id = report._persist(conn, rep, json.dumps(
                    {"phase": 13, "state": name, "retrieve": cfg.switches(), "eval": ecfg}, ensure_ascii=False),
                    run_id=f"p13-{name}-{ts}")
                out["states"][name] = {"switches": cfg.switches(), "aggregate": rep["aggregate"],
                                       "per_question": rep["per_question"], "labeled": rep["labeled"]}
                out["run_ids"][name] = run_id
                if name in SWEEP_STATES and Path(seed_path).exists():
                    out["sweeps"][name] = gen_cli.sweep(config_path, seed_path, retriever=r)
            finally:
                r.close()
    finally:
        if own_conn:
            conn.close()
    sections = Path(out_dir) / "sections_report.json"
    out["sections"] = json.loads(sections.read_text(encoding="utf-8")) if sections.exists() else None
    write_report(out, Path(out_dir))
    return out


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.4f}"


def _sweep_block(sw: dict) -> list[str]:
    lines = ["```", f"{'qid':6} {'gold':11} {'single_source':13} {'would_abstain':13} uncovered_terms"]
    for r in sw["rows"]:
        lines.append(f"{r['qid']:6} {str(r['gold']):11} {str(r['single_source']):13} {str(r['would_abstain']):13} "
                     f"{', '.join(r['uncovered_terms'])}")
    lines += ["", f"answerable questions that would abstain: {sw['answerable_would_abstain']}",
              f"abstain questions that would answer:     {sw['abstain_would_answer']}", "```"]
    return lines


def write_report(out: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retrieval_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    states = out["states"]
    metrics = list(next(iter(states.values()))["aggregate"].keys()) if states else []
    lines = ["# Phase 13 retrieval report", "",
             f"run {out['ts']} (UTC); one eval_runs row per state, ids `p13-<state>-{out['ts']}`", "",
             "Pooled values: gold was labeled from the BASELINE retriever's top-30 (Phase 7), so",
             "recall and nDCG denominators are that judged pool, not the corpus. A state that",
             "surfaces passages the labels never saw cannot be credited for them; unjudged@k is the",
             "share of each top-k with no human label at all. Read the two columns together.", "",
             "## State table (aggregate over labeled questions)", "",
             "| state | " + " | ".join(metrics) + " |", "| --- | " + " | ".join("---:" for _ in metrics) + " |"]
    for name, st in states.items():
        lines.append(f"| {name} | " + " | ".join(_fmt(st["aggregate"].get(m)) for m in metrics) + " |")
    lines += ["", "Switch states:", ""]
    for name, st in states.items():
        sw = st["switches"]
        on = [k for k, v in sw.items() if v is True] + ([f"per_item_cap={sw['per_item_cap']}"] if sw["per_item_cap"] else [])
        lines.append(f"- {name}: {', '.join(on) if on else 'all off'}")
    base = states.get("baseline")
    for target in ("all_on_cap3", "all_on_cap5"):
        if base and target in states:
            lines += ["", f"## Per-question change, {target} vs baseline (questions that moved)", "",
                      "| qid | gold | recall@10 base -> new | ndcg@10 base -> new | unjudged@10 new |", "| --- | --- | --- | --- | ---: |"]
            bq = {r["qid"]: r for r in base["per_question"]}
            for r in states[target]["per_question"]:
                b = bq.get(r["qid"], {})
                if (b.get("recall@10"), b.get("ndcg@10")) == (r.get("recall@10"), r.get("ndcg@10")):
                    continue
                gold = "answerable" if r["answerable"] else "abstain"
                lines.append(f"| {r['qid']} | {gold} | {_fmt(b.get('recall@10'))} -> {_fmt(r.get('recall@10'))} | "
                             f"{_fmt(b.get('ndcg@10'))} -> {_fmt(r.get('ndcg@10'))} | {_fmt(r.get('unjudged@10'))} |")
    for name in SWEEP_STATES:
        if name in out["sweeps"]:
            lines += ["", f"## Thinness sweep, state {name} (retrieval + frozen rule, no model call)", ""]
            lines += _sweep_block(out["sweeps"][name])
    sec = out.get("sections")
    if sec:
        lines += ["", "## Section classifier (ingest.sections, one-time; copied from sections_report.md)", "",
                  f"- pages classified: {sec['pages_classified']}; NULL (no text): {sec['pages_unclassified_no_text']}"]
        for c in ("front", "body", "back"):
            lines.append(f"- {c}: {sec['counts'][c]} pages, {sec['passages_by_class'].get(c, 0)} passages")
        lines += ["", "| method | pages |", "| --- | ---: |"]
        for m, n in sec["methods"].items():
            lines.append(f"| {m} | {n} |")
        for c in ("front", "body", "back"):
            lines += ["", f"### Sample: {c}", ""]
            for r in sec["samples"][c]:
                title = " ".join(str(r["title"] or "").split())[:70]
                lines.append(f"- `{r['page_id']}` leaf {r['leaf']}/{r['n_leaves']} [{r['method']}] {title}")
                lines.append(f"  > {r['excerpt']}")
    (out_dir / "retrieval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only: picks up CIVIC_*_PATH from .env; never overrides a set variable
    load_dotenv()
    p = argparse.ArgumentParser(description="Phase 13 retrieval sweep over switch states.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--seed", default=Path("eval/seed_questions.jsonl"), type=Path)
    p.add_argument("--out", default=OUT_DIR, type=Path)
    args = p.parse_args(argv)
    out = run(args.config, seed_path=args.seed, out_dir=args.out)
    print(json.dumps({name: st["aggregate"] for name, st in out["states"].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
