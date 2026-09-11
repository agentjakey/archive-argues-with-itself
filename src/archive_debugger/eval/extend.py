"""Pooled-labels extension (Phase 13). Gold was pooled from the baseline retriever's
top-30, so a changed ranking surfaces passages no human has judged. This module:

- build: writes a worksheet of every passage in the CANDIDATE retriever's top-N for
  each question that has no label yet, in the Phase 7 assist format (advisory
  proposals only, never written as gold), blind to which switch surfaced it.
- apply: applies Jake's reviewed decisions ADDITIVELY: new (qid, passage) labels
  only; an existing label is never overwritten (N4); a verdict changes only when
  the decisions say so, and every change is returned for the changelog."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from archive_debugger.eval import assist, store
from archive_debugger.eval.label import _read_worksheet, filters_from
from archive_debugger.eval.retrieval_sweep import CANDIDATE
from archive_debugger.ingest import db
from archive_debugger.retrieve.config import RetrieveConfig, load_retrieve_config

OUT_DEFAULT = Path("reports/phase13/extension_worksheet.jsonl")
GOLD_DEFAULT = Path("eval/gold_decisions_phase13.json")


def candidate_config(base: RetrieveConfig) -> RetrieveConfig:
    return replace(base, **CANDIDATE)


def build_records(conn, retriever, *, top_n: int = 20, end_year: int = 2009) -> tuple[list[dict], dict]:
    records: list[dict] = []
    stats = {"questions_with_new": 0, "candidates": 0, "per_question": {}}
    for q in store.list_questions(conn):
        hits = retriever.search(q["text"], filters=filters_from(q), top_k=top_n)
        judged = set(store.get_labels(conn, q["qid"]))
        new = [(rank, h) for rank, h in enumerate(hits, start=1) if h["passage_id"] not in judged]
        if not new:
            continue
        recs = assist.build_records(q, [h for _, h in new], end_year)
        for rec, (rank, _) in zip(recs[1:], new):
            rec["rank"] = rank                     # the candidate's own rank, so decisions cite it
        records.extend(recs)
        stats["questions_with_new"] += 1
        stats["candidates"] += len(new)
        stats["per_question"][q["qid"]] = len(new)
    return records, stats


def run(config_path: Path, *, out_path: Optional[Path] = None, top_n: int = 20, conn=None, retriever=None,
        embedder=None) -> dict:
    own_conn = conn is None
    if own_conn:
        db_path = db.resolve_db_path(config_path)
        if not Path(db_path).exists():
            raise FileNotFoundError(f"civic.db not found at {db_path}; set CIVIC_DB_PATH or fix [index].db_path")
        conn = db.init_db(db_path)
    own_retriever = retriever is None
    if own_retriever:
        from archive_debugger.retrieve.search import Retriever  # lazy: no fastembed at import
        retriever = Retriever(None, cfg=candidate_config(load_retrieve_config(config_path)), embedder=embedder)
    out_path = Path(out_path) if out_path else OUT_DEFAULT
    try:
        _, end_year = assist._eval_cfg(config_path)
        records, stats = build_records(conn, retriever, top_n=top_n, end_year=end_year)
    finally:
        if own_retriever:
            retriever.close()
        if own_conn:
            conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats["path"] = str(out_path)
    stats["top_n"] = top_n
    return stats


def apply_extension(conn, worksheet_path: Path, decisions: dict) -> dict:
    """decisions: {qid: {"r": [ranks], "u": [ranks] (optional), "v": "a"|"x" (optional)}}.
    Every candidate in the worksheet for a listed qid gets a label: 1 for "r" ranks, 0
    for the rest, EXCEPT "u" (uncertain) ranks, which receive no label and stay unjudged
    (a judgment is never manufactured from a doubt). All-or-nothing validation; a
    passage that already carries a label is a hard error."""
    order, summaries, cands = _read_worksheet(worksheet_path)
    decisions = {k: v for k, v in decisions.items() if k != "_meta"}
    plan, verdicts = [], []
    for qid, dec in decisions.items():
        if qid not in summaries:
            raise ValueError(f"{qid}: not in the extension worksheet")
        by_rank = {c["rank"]: c for c in cands.get(qid, [])}
        rset, uset = set(dec.get("r", [])), set(dec.get("u", []))
        missing = sorted(r for r in (rset | uset) if r not in by_rank)
        if missing:
            raise ValueError(f"{qid}: ranks {missing} have no worksheet record")
        if rset & uset:
            raise ValueError(f"{qid}: ranks {sorted(rset & uset)} are both relevant and uncertain")
        existing = store.get_labels(conn, qid)
        clash = sorted(c["passage_id"] for c in by_rank.values() if c["passage_id"] in existing)
        if clash:
            raise ValueError(f"{qid}: already labeled, extension is additive only: {clash}")
        rows = [(c["passage_id"], 1 if rank in rset else 0) for rank, c in sorted(by_rank.items()) if rank not in uset]
        skipped = [c["passage_id"] for rank, c in sorted(by_rank.items()) if rank in uset]
        v = dec.get("v")
        if v is not None and v not in ("a", "x"):
            raise ValueError(f"{qid}: verdict must be 'a', 'x' or absent, got {v!r}")
        plan.append((qid, rows, skipped, v))
    for qid, rows, _skipped, v in plan:
        for passage_id, relevance in rows:
            store.write_label(conn, qid, passage_id, relevance)
        if v is not None:
            before = store.gold_verdict(conn, qid)
            new = 1 if v == "a" else 0
            if before is None or before["answerable"] != new:
                store.write_gold(conn, qid, new)
                verdicts.append({"qid": qid, "from": None if before is None else before["answerable"], "to": new})
    return {
        "qids": len(plan),
        "labels": sum(len(rows) for _, rows, _, _ in plan),
        "relevant": sum(rel for _, rows, _, _ in plan for _, rel in rows),
        "uncertain_unlabeled": sum(len(s) for _, _, s, _ in plan),
        "verdict_changes": verdicts,
    }


def write_gold_file(decisions: dict, path: Path, *, meta: str) -> None:
    body = {"_meta": {"source": meta, "applied_ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}}
    body.update({k: v for k, v in decisions.items() if k != "_meta"})
    Path(path).write_text(json.dumps(body, ensure_ascii=False, indent=0).replace("\n{", "{"), encoding="utf-8")


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv()
    p = argparse.ArgumentParser(description="Phase 13 pooled-labels extension: worksheet build / additive apply.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default=None, type=Path)
    p.add_argument("--top-n", dest="top_n", default=20, type=int)
    p.add_argument("--apply", default=None, type=Path, help="decisions JSON to apply against --worksheet (additive)")
    p.add_argument("--worksheet", default=OUT_DEFAULT, type=Path)
    args = p.parse_args(argv)
    if args.apply:
        conn = db.init_db(db.resolve_db_path(args.config))
        try:
            summary = apply_extension(conn, args.worksheet, json.loads(args.apply.read_text(encoding="utf-8")))
        finally:
            conn.close()
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    stats = run(args.config, out_path=args.out, top_n=args.top_n)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
