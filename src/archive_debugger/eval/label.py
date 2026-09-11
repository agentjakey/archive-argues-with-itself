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


def _eval_top_n(config_path: Path) -> int:
    with Path(config_path).open("rb") as fh:
        return int(tomllib.load(fh).get("eval", {}).get("label_top_n", 30))


def run(config_path=None, *, conn=None, qid=None, top_n=None, revise=False,
        prompt_fn=input, print_fn=print, retriever=None) -> None:
    own_conn = conn is None
    if own_conn:
        conn = db.init_db(db.resolve_db_path(config_path))
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
        if own_conn:
            conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Human labeling harness (writes YOUR gold labels).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--qid", default=None, help="label/revise a single question")
    p.add_argument("--top-n", type=int, default=None)
    p.add_argument("--revise", action="store_true", help="re-open already-labeled questions")
    args = p.parse_args(argv)
    run(args.config, qid=args.qid, top_n=args.top_n, revise=args.revise)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
