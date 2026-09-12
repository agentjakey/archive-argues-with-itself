"""Phase 13 retrieval-quality sweep: the full Phase 7 eval (recall@k, nDCG@10, plus
unjudged@10/@20) on the current retriever under each switch state, persisted as
one eval_runs row per state, plus the no-model abstention sweep on the baseline
and the all-on states. Writes the machine report to reports/phase13/ (retrieval_report.md
and .json plus per-state checkpoints); the curated evidence copy that carries the
hand-written final section lives at docs/evaluation/retrieval_report.md.

States: baseline (all off), each switch alone (cap at 3 and at 5 separately;
later_years is a recorded no-op for ranking), all on with cap 3, all on with cap 5.

Pooled-labels caveat, printed in the report: gold was labeled from the BASELINE
retriever's top-30, so a ranking that surfaces new passages cannot be credited for
them; unjudged@k says how much of each top-k the labels cannot see."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
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
# Every state spells out all five switches, so the table means the same thing whatever
# config/pilot.toml currently has turned on (the candidate is on there after Phase 13).
# Section weights and pool_size still come from config.
_OFF = {"section_demote": False, "fts_drop_stopwords": False, "doc_type_family_filter": False,
        "later_years_flag": False, "per_item_cap": 0}
_ALL = {"section_demote": True, "fts_drop_stopwords": True, "doc_type_family_filter": True, "later_years_flag": True}
STATES: list[tuple[str, dict]] = [
    ("baseline", {**_OFF}),                                          # Phase 7 retrieval
    ("section_demote", {**_OFF, "section_demote": True}),
    ("fts_drop_stopwords", {**_OFF, "fts_drop_stopwords": True}),
    ("doc_type_family_filter", {**_OFF, "doc_type_family_filter": True}),
    ("cap3", {**_OFF, "per_item_cap": 3}),
    ("cap5", {**_OFF, "per_item_cap": 5}),
    ("later_years", {**_OFF, "later_years_flag": True}),           # annotation only; ranking identical to baseline
    ("all_on_cap3", {**_ALL, "per_item_cap": 3}),
    ("all_on_cap5", {**_ALL, "per_item_cap": 5}),
    # The Phase 13 candidate: every switch on, cap 5, section weights from config
    # ([retrieve].section_weight_front/back), so the back weight follows the
    # classifier-precision decision rather than a hard-coded value.
    ("candidate", {**_ALL, "per_item_cap": 5}),
]
CANDIDATE = dict(STATES)["candidate"]
SWEEP_STATES = ("baseline", "all_on_cap3", "all_on_cap5", "candidate")


def _state_file(out_dir: Path, name: str) -> Path:
    return Path(out_dir) / "states" / f"{name}.json"


class DenseMemo:
    """On-disk memo of the dense leg. The dense candidate list for a query depends only
    on the query vector, the WHERE clause and its params, k, and the index file, none
    of which the Phase 13 switches change (except the family filter's WHERE, which is
    part of the key), so states after the first reuse it instead of re-scanning 745k
    vectors per question. Keys include the index file's size and mtime."""

    def __init__(self, path: Path, index_path: Path):
        self.path = Path(path)
        st = Path(index_path).stat()
        self.index_tag = f"{st.st_size}:{st.st_mtime_ns}"
        self.data: dict = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.hits = self.misses = 0

    def key(self, qvec, where, params, k) -> str:
        material = json.dumps([self.index_tag, [round(x, 7) for x in qvec], where, params, k])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def wrap(self, retriever: Retriever) -> None:
        inner = retriever._dense

        def cached(qvec, where, params, k):
            key = self.key(qvec, where, params, k)
            if key in self.data:
                self.hits += 1
                return list(self.data[key])
            self.misses += 1
            out = inner(qvec, where, params, k)
            self.data[key] = out
            return out

        retriever._dense = cached  # type: ignore[method-assign]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")


def run(config_path: Path, *, seed_path: Path = Path("eval/seed_questions.jsonl"), out_dir: Path = OUT_DIR,
        embedder=None, conn=None, states: Optional[list] = None, only: Optional[list[str]] = None,
        resume: bool = True, dense_memo: bool = True, gold: str = "phase7", progress=print) -> dict:
    """Evaluate each state, checkpointing one JSON per state under out_dir/states so an
    interrupted sweep resumes; `only` restricts this call to named states; the report is
    assembled from every checkpoint present. `gold` names the label set scored against
    and is recorded in every eval_runs row (N4: gold extensions are recorded)."""
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
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    section_rows = conn.execute("SELECT COUNT(section_class) FROM pages").fetchone()[0]
    out_dir = Path(out_dir)
    todo = [(n, o) for n, o in (states or STATES) if only is None or n in only]
    memo = DenseMemo(out_dir / "states" / "dense_memo.json", base.index_path) if dense_memo else None
    try:
        for name, over in todo:
            path = _state_file(out_dir, name)
            if resume and path.exists():
                progress(f"state {name}: checkpoint present, skipped")
                continue
            cfg = replace(base, **over)
            if cfg.section_demote and section_rows == 0:
                raise RuntimeError("pages.section_class is empty: run `python -m archive_debugger.ingest.sections` first")
            embedder = embedder or make_embedder(base.embedder, base.embedding_model, base.embedding_dim)
            t0 = time.perf_counter()
            r = Retriever(None, cfg=cfg, embedder=embedder)
            if memo is not None:
                memo.wrap(r)
            try:
                rep = report.evaluate(conn, r, recall_ks=recall_ks, ndcg_k=ndcg_k,
                                      min_relevant=int(ecfg.get("abstention_min_relevant", 1)), top_n=top_n)
                run_id = report._persist(conn, rep, json.dumps(
                    {"phase": 13, "state": name, "gold": gold, "retrieve": cfg.switches(), "eval": ecfg},
                    ensure_ascii=False), run_id=f"p13-{name}-{ts}")
                state = {"name": name, "ts": ts, "run_id": run_id, "gold": gold, "switches": cfg.switches(),
                         "aggregate": rep["aggregate"], "per_question": rep["per_question"], "labeled": rep["labeled"],
                         "sweep": None, "seconds": None}
                if name in SWEEP_STATES and Path(seed_path).exists():
                    state["sweep"] = gen_cli.sweep(config_path, seed_path, retriever=r)
                state["seconds"] = round(time.perf_counter() - t0, 1)
            finally:
                r.close()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            if memo is not None:
                memo.save()
                progress(f"state {name}: done in {state['seconds']} s, run_id {run_id} "
                         f"(dense memo hits {memo.hits}, misses {memo.misses})")
            else:
                progress(f"state {name}: done in {state['seconds']} s, run_id {run_id}")
    finally:
        if own_conn:
            conn.close()
    return assemble(out_dir, states=states)


def assemble(out_dir: Path, *, states: Optional[list] = None) -> dict:
    """Build the report from whatever state checkpoints exist, in canonical order."""
    out_dir = Path(out_dir)
    out: dict = {"ts": None, "states": {}, "sweeps": {}, "run_ids": {}}
    for name, _ in (states or STATES):
        path = _state_file(out_dir, name)
        if not path.exists():
            continue
        st = json.loads(path.read_text(encoding="utf-8"))
        out["ts"] = out["ts"] or st["ts"]
        out["states"][name] = {"switches": st["switches"], "aggregate": st["aggregate"],
                               "per_question": st["per_question"], "labeled": st["labeled"],
                               "run_id": st["run_id"], "ts": st["ts"], "seconds": st.get("seconds")}
        out["run_ids"][name] = st["run_id"]
        if st.get("sweep"):
            out["sweeps"][name] = st["sweep"]
    sections = out_dir / "sections_report.json"
    out["sections"] = json.loads(sections.read_text(encoding="utf-8")) if sections.exists() else None
    if out["states"]:
        write_report(out, out_dir)
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
    runs = ", ".join(f"`{st['run_id']}`" for st in states.values() if st.get("run_id"))
    lines = ["# Phase 13 retrieval report", "",
             f"one eval_runs row per state: {runs}", "",
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
                  f"- pages classified: {sec['pages_classified']}; NULL (no text): {sec['pages_unclassified_null']}; "
                  f"{sec['timing']['pages_per_s']} pages/s"]
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
    p.add_argument("--state", action="append", default=None, help="run only this state (repeatable); default all")
    p.add_argument("--report-only", action="store_true", help="assemble the report from existing checkpoints")
    p.add_argument("--no-resume", action="store_true", help="recompute states even when a checkpoint exists")
    p.add_argument("--gold", default="phase7", help="name of the label set scored against, recorded in eval_runs")
    args = p.parse_args(argv)
    if args.report_only:
        out = assemble(args.out)
    else:
        out = run(args.config, seed_path=args.seed, out_dir=args.out, only=args.state, resume=not args.no_resume,
                  gold=args.gold)
    print(json.dumps({name: st["aggregate"] for name, st in out["states"].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
