"""Human labeling harness. Runs the REAL retriever, shows the top-N candidates for
MY review, and records MY relevance judgments and MY answerable/should-abstain
verdict as the gold labels. Never pre-fills a judgment (N4). Resumable and
revisable. The candidate ranking is retrieval output for review only; the score is
deliberately NOT shown so it cannot anchor a relevance call."""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

from archive_debugger.eval import store
from archive_debugger.ingest import db
from archive_debugger.retrieve.filters import Filters


def filters_from(q: dict) -> Filters:
    f = json.loads(q.get("filters_json") or "{}")
    return Filters(period=f.get("period"), jurisdiction=f.get("jurisdiction"),
                   doc_type=f.get("doc_type"), min_ocr=float(f.get("min_ocr", 0.0) or 0.0))


def _fmt(i: int, h: dict) -> str:
    excerpt = " ".join((h.get("text") or "").split())[:280]
    return "\n".join([
        f"[{i}] year={h.get('year')}  {h.get('jurisdiction')}  {h.get('doc_type')}  ocr={h.get('ocr_quality')}",
        f"     {h.get('title')}  (leaf {h['leaf_index']}, printed p.{h.get('printed_page')})",
        f"     {h['page_deep_link']}",
        f"     {excerpt}",
    ])


def label_question(q, retriever, conn, top_n, prompt_fn, print_fn, existing=None) -> None:
    hits = retriever.search(q["text"], filters=filters_from(q), top_k=top_n)
    print_fn(f"\n=== {q['qid']}  [{q.get('qtype')}]  topic={q.get('topic')} ===")
    print_fn(q["text"])
    if not hits:
        print_fn("(no candidates returned -- likely a real coverage gap)")
    for i, h in enumerate(hits):
        print_fn(_fmt(i, h))
        cur = None if existing is None else existing.get(h["passage_id"])
        tag = "" if cur is None else f" [current: {'relevant' if cur else 'not'}]"
        ans = prompt_fn(f"  [{i}] r=relevant / n=not / s=skip{tag}: ").strip().lower()
        if ans == "r":
            store.write_label(conn, q["qid"], h["passage_id"], 1)
        elif ans == "n":
            store.write_label(conn, q["qid"], h["passage_id"], 0)
        # 's' or empty: no judgment written (no pre-fill, no forced label)
    verdict = ""
    while verdict not in ("a", "x"):
        verdict = prompt_fn("  QUESTION verdict -- a=answerable / x=should-abstain: ").strip().lower()
    store.write_gold(conn, q["qid"], 1 if verdict == "a" else 0)
    print_fn(f"  saved {q['qid']}")


def _fmt_ws(c: dict) -> str:
    proposed = "relevant" if c.get("proposed_relevance") else "not"
    return "\n".join([
        f"[{c.get('rank')}] year={c.get('year')}  {c.get('jurisdiction')}  {c.get('doc_type')}  ocr={c.get('ocr_quality')}",
        f"     {c.get('title')}  (leaf {c.get('leaf_index')}, printed p.{c.get('printed_page')})",
        f"     {c.get('deep_link')}",
        f"     {c.get('excerpt')}",
        f"     [proposed: {proposed}] {c.get('reason', '')}",
    ])


def _read_worksheet(path):
    order, summaries, cands = [], {}, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        qid = r.get("qid")
        if r.get("kind") == "summary":
            if qid not in summaries:
                order.append(qid)
            summaries[qid] = r
        elif r.get("kind") == "candidate":
            cands.setdefault(qid, []).append(r)
    for qid in cands:
        cands[qid].sort(key=lambda c: c.get("rank", 0))
    return order, summaries, cands


def label_from_worksheet(summary, candidates, conn, prompt_fn, print_fn, existing=None) -> None:
    print_fn(f"\n=== {summary['qid']}  [{summary.get('qtype')}] ===")
    print_fn(summary.get("text", ""))
    for c in candidates:
        print_fn(_fmt_ws(c))
        cur = None if existing is None else existing.get(c["passage_id"])
        tag = "" if cur is None else f" [current: {'relevant' if cur else 'not'}]"
        ans = prompt_fn(f"  [{c.get('rank')}] r=relevant / n=not / s=skip "
                        f"(blank does NOT accept the proposal){tag}: ").strip().lower()
        if ans == "r":
            store.write_label(conn, summary["qid"], c["passage_id"], 1)
        elif ans == "n":
            store.write_label(conn, summary["qid"], c["passage_id"], 0)
        # blank / s / anything else: no write -- the proposal is never auto-accepted
    proposed = "answerable" if summary.get("proposed_answerable") else "should-abstain"
    v = prompt_fn(f"  QUESTION verdict -- a=answerable / x=should-abstain "
                  f"(proposed: {proposed}; a key is required, blank skips): ").strip().lower()
    if v == "a":
        store.write_gold(conn, summary["qid"], 1)
    elif v == "x":
        store.write_gold(conn, summary["qid"], 0)
    # blank / anything else: no gold written -- question stays unlabeled
    print_fn(f"  {summary['qid']} reviewed")


def _load_decisions(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k != "_meta"}


def apply_decisions(conn, worksheet_path, decisions_path, *, expected_qids=50, candidates_per_q=30) -> dict:
    """Non-interactive apply of reviewed decisions. For each qid, the listed 'r'
    ranks are relevant (1); every other rank 1..candidates_per_q is not-relevant
    (0); 'v' is the verdict (a->answerable, x->abstain). Writes through the SAME
    store.py writers the interactive path uses (revise semantics: clear then write).
    All-or-nothing: everything is validated before any write."""
    order, summaries, cands = _read_worksheet(worksheet_path)
    decisions = _load_decisions(decisions_path)

    if len(decisions) != expected_qids:
        raise ValueError(f"decisions cover {len(decisions)} qids, expected exactly {expected_qids}")
    plan = []
    for qid, dec in decisions.items():
        if qid not in summaries:
            raise ValueError(f"{qid}: missing from worksheet")
        cs = cands.get(qid, [])
        if len(cs) != candidates_per_q:
            raise ValueError(f"{qid}: worksheet has {len(cs)} candidates, expected {candidates_per_q}")
        v = dec.get("v")
        if v not in ("a", "x"):
            raise ValueError(f"{qid}: verdict must be 'a' or 'x', got {v!r}")
        by_rank = {c.get("rank"): c for c in cs}
        rset = set(dec.get("r", []))
        for rank in rset:
            if rank not in by_rank:
                raise ValueError(f"{qid}: relevant rank {rank} has no worksheet record")
        rows = []
        for rank in range(1, candidates_per_q + 1):
            c = by_rank.get(rank)
            if c is None:
                raise ValueError(f"{qid}: worksheet missing rank {rank}")
            rows.append((c["passage_id"], 1 if rank in rset else 0))
        plan.append((qid, rows, 1 if v == "a" else 0))

    for qid, rows, answerable in plan:
        store.clear_labels(conn, qid)          # revise: drop any prior labels/verdict
        for passage_id, relevance in rows:
            store.write_label(conn, qid, passage_id, relevance)
        store.write_gold(conn, qid, answerable)

    return {
        "qids": len(plan),
        "labels": sum(len(rows) for _, rows, _ in plan),
        "relevant": sum(rel for _, rows, _ in plan for _, rel in rows),
        "answerable": sum(1 for _, _, a in plan if a == 1),
        "abstain": sum(1 for _, _, a in plan if a == 0),
    }


def _eval_top_n(config_path: Path) -> int:
    with Path(config_path).open("rb") as fh:
        return int(tomllib.load(fh).get("eval", {}).get("label_top_n", 30))


def run(config_path=None, *, conn=None, qid=None, top_n=None, revise=False,
        prompt_fn=input, print_fn=print, retriever=None, worksheet=None) -> None:
    own_conn = conn is None
    if own_conn:
        conn = db.init_db(db.resolve_db_path(config_path))
    try:
        if worksheet is not None:
            order, summaries, cands = _read_worksheet(worksheet)
            targets = [qid] if qid else order
            for qq in [x for x in targets if x in summaries]:
                labeled = store.is_labeled(conn, qq)
                if labeled and not revise:
                    print_fn(f"skip {qq} (already labeled; use --revise to edit)")
                    continue
                existing = store.get_labels(conn, qq) if (labeled and revise) else None
                label_from_worksheet(summaries[qq], cands.get(qq, []), conn, prompt_fn, print_fn, existing=existing)
            return
        if top_n is None:
            top_n = _eval_top_n(config_path) if config_path is not None else 30
        own_retriever = retriever is None
        if own_retriever:
            from archive_debugger.retrieve.search import Retriever  # lazy: keeps import light
            retriever = Retriever(config_path)
        try:
            questions = [store.get_question(conn, qid)] if qid else store.list_questions(conn)
            for q in [x for x in questions if x]:
                labeled = store.is_labeled(conn, q["qid"])
                if labeled and not revise:
                    print_fn(f"skip {q['qid']} (already labeled; use --revise to edit)")
                    continue
                existing = store.get_labels(conn, q["qid"]) if (labeled and revise) else None
                label_question(q, retriever, conn, top_n, prompt_fn, print_fn, existing=existing)
        finally:
            if own_retriever:
                retriever.close()
    finally:
        if own_conn:
            conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Human labeling harness (writes YOUR gold labels).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--qid", default=None, help="label/revise a single question")
    p.add_argument("--top-n", type=int, default=None)
    p.add_argument("--revise", action="store_true", help="re-open already-labeled questions")
    p.add_argument("--from-worksheet", dest="worksheet", default=None, type=Path,
                   help="review advisory proposals from label_worksheet.jsonl instead of live retrieval")
    p.add_argument("--apply-decisions", dest="apply_decisions", default=None, type=Path,
                   help="non-interactive: apply a reviewed decisions JSON against the worksheet")
    args = p.parse_args(argv)
    if args.apply_decisions:
        if not args.worksheet:
            p.error("--apply-decisions requires --from-worksheet")
        conn = db.init_db(db.resolve_db_path(args.config))
        try:
            summary = apply_decisions(conn, args.worksheet, args.apply_decisions)
        finally:
            conn.close()
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    run(args.config, qid=args.qid, top_n=args.top_n, revise=args.revise, worksheet=args.worksheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
