"""Generate CLI: answer one question with cited synthesis, or sweep the eval
questions through retrieval + thinness only (no model call) to preview abstention.
The configured LLM provider is the only network call (N1); --provider stub keeps the
whole path offline. Retrieval config is loaded the same way eval does (Retriever).

.env support lives ONLY here (load_dotenv at the top of main), never in llm.py or
answer.py, so the import guard and test hermeticity are unchanged."""
from __future__ import annotations

import argparse
import functools
import json
import tomllib
from pathlib import Path
from typing import Optional

from archive_debugger.eval import store
from archive_debugger.eval.questions import load_seed
from archive_debugger.generate.answer import compose, coverage_of, is_thin
from archive_debugger.generate.llm import make_llm
from archive_debugger.retrieve import citation
from archive_debugger.retrieve.filters import Filters
from archive_debugger.retrieve.search import Retriever


def load_generate_config(config_path: Path) -> dict:
    with Path(config_path).open("rb") as fh:
        g = tomllib.load(fh).get("generate", {})
    return {
        "provider": g.get("provider", "anthropic"),
        "model": g.get("model", "claude-haiku-4-5-20251001"),
        "max_tokens": int(g.get("max_tokens", 2048)),
        "top_k": int(g.get("top_k", 12)),
        "min_passages": int(g.get("min_passages", 3)),
    }


def _filters(d: Optional[dict]) -> Filters:
    d = d or {}
    return Filters(period=d.get("period"), jurisdiction=d.get("jurisdiction"),
                   doc_type=d.get("doc_type"), min_ocr=float(d.get("min_ocr", 0.0) or 0.0))


def answer_question(config_path: Path, question: str, *, provider: Optional[str] = None,
                    top_k: Optional[int] = None, filters: Optional[dict] = None,
                    retriever: Optional[Retriever] = None) -> dict:
    gcfg = load_generate_config(config_path)
    own = retriever is None
    retriever = retriever or Retriever(config_path)
    try:
        hits = retriever.search(question, filters=_filters(filters), top_k=top_k or gcfg["top_k"])
        llm = make_llm(provider or gcfg["provider"], gcfg["model"], gcfg["max_tokens"])
        verify = functools.partial(citation.verify_citations, retriever.conn)
        return compose(question, hits, llm, verify, min_passages=gcfg["min_passages"]).to_dict()
    finally:
        if own:
            retriever.close()


def sweep(config_path: Path, seed_path: Path, *, top_k: Optional[int] = None,
          retriever: Optional[Retriever] = None) -> dict:
    """Retrieval + thinness for every seed question. NO model is constructed or called."""
    gcfg = load_generate_config(config_path)
    own = retriever is None
    retriever = retriever or Retriever(config_path)
    rows = []
    try:
        for q in load_seed(seed_path):
            hits = retriever.search(q["text"], filters=_filters(q.get("filters")), top_k=top_k or gcfg["top_k"])
            cov = coverage_of(q["text"], hits)
            gold = store.gold_verdict(retriever.conn, q["qid"])
            rows.append({
                "qid": q["qid"],
                "gold": None if gold is None else ("answerable" if gold["answerable"] else "abstain"),
                "uncovered_terms": cov.uncovered_terms,
                "single_source": cov.single_source,
                "would_abstain": is_thin(cov, min_passages=gcfg["min_passages"]),
            })
    finally:
        if own:
            retriever.close()
    return {
        "rows": rows,
        "answerable_would_abstain": sum(1 for r in rows if r["gold"] == "answerable" and r["would_abstain"]),
        "abstain_would_answer": sum(1 for r in rows if r["gold"] == "abstain" and not r["would_abstain"]),
        "unlabeled": sum(1 for r in rows if r["gold"] is None),
    }


def _print_sweep(result: dict) -> None:
    print(f"{'qid':6} {'gold':11} {'single_source':13} {'would_abstain':13} uncovered_terms")
    for r in result["rows"]:
        print(f"{r['qid']:6} {str(r['gold']):11} {str(r['single_source']):13} {str(r['would_abstain']):13} "
              f"{', '.join(r['uncovered_terms'])}")
    print()
    print(f"answerable questions that would abstain: {result['answerable_would_abstain']}")
    print(f"abstain questions that would answer:     {result['abstain_would_answer']}")
    if result["unlabeled"]:
        print(f"unlabeled questions (no gold verdict):   {result['unlabeled']}")


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI-only: never imported by llm.py / answer.py
    load_dotenv()  # default: does NOT override variables already set in the environment

    p = argparse.ArgumentParser(description="Cited synthesis over the civic corpus, or a no-model abstention sweep.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--question", default=None)
    p.add_argument("--provider", choices=["stub", "anthropic"], default=None, help="override [generate].provider")
    p.add_argument("--top-k", dest="top_k", type=int, default=None)
    p.add_argument("--sweep", default=None, type=Path,
                   help="seed_questions.jsonl: run retrieval + thinness only for every question; no model call")
    args = p.parse_args(argv)
    if args.sweep:
        _print_sweep(sweep(args.config, args.sweep, top_k=args.top_k))
        return 0
    if not args.question:
        p.error("provide --question or --sweep")
    print(json.dumps(answer_question(args.config, args.question, provider=args.provider, top_k=args.top_k),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
