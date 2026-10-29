"""Tokens and cost per uncached answer, for seed and story questions only, with no paid call.

For each seed question (and each story's asked question) in one scope, this builds the exact
request the server would send on a cache miss: the same sanitizing, retrieval, abstention gate
(generate.answer.compose) and prompt (generate.prompt), captured by a recording stand-in for the
model. Input tokens are then counted with the free count_tokens endpoint, with the same model,
system prompt, user message and output_format=Draft that AnthropicLLM.draft sends. A question the
gate abstains on makes no model call and costs nothing.

Output tokens cannot be counted without generating. They are estimated from the v1 judgment
worksheets (reports/phase16, reports/microlog), which hold each seed answer's sentences and
citations: the Draft JSON is rebuilt from them and counted the same way, minus the count of an
empty message. That is a lower bound (sentences the verifier dropped are not in the worksheets).

Visitor questions are never read: the answer cache is not opened.

    python scripts/v2/answer_cost.py --scope pilot --out reports/v2/raw/cost_pilot.json
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import statistics
import sys
import time
from pathlib import Path

# USD per million tokens. Claude Haiku 4.5: $1 input, $5 output (Anthropic pricing, checked
# 2026-10-29 against the v2 brief); batch is half price and is not used by the server.
PRICES = {"claude-haiku-4-5-20251001": (1.00, 5.00), "claude-haiku-4-5": (1.00, 5.00)}
SEEDS = {"pilot": "eval/seed_questions.jsonl", "microlog": "config/seed_questions.microlog.jsonl"}
STORIES = {"pilot": "config/stories.json", "microlog": "config/stories.microlog.json"}
WORKSHEETS = {"pilot": "reports/phase16/judgment_worksheet.jsonl", "microlog": "reports/microlog/judgment_worksheet.jsonl"}
PAUSE_S = 0.7   # between count_tokens calls; the endpoint has its own rate limit


class RecordingLLM:
    """Stands in for the model: records the request compose() would send and returns an empty
    draft, so no generation happens."""

    def __init__(self):
        self.calls = []

    def draft(self, system: str, user: str):
        from archive_debugger.generate.llm import Draft
        self.calls.append((system, user))
        return Draft(sentences=[])


def read_jsonl(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def questions_for(scope: str) -> list[dict]:
    from archive_debugger.editorial import asked_question, load_stories
    out = [{"id": q["qid"], "kind": "seed", "text": q["text"], "filters": q.get("filters") or {}}
           for q in read_jsonl(SEEDS[scope])]
    seen = {(q["text"], json.dumps(q["filters"], sort_keys=True)) for q in out}
    for s in load_stories(Path(STORIES[scope])):
        key = (asked_question(s), json.dumps(s.get("filters") or {}, sort_keys=True))
        if key not in seen:
            out.append({"id": s["id"], "kind": "story", "text": key[0], "filters": s.get("filters") or {}})
            seen.add(key)
    return out


def worksheet_drafts(scope: str) -> dict:
    """qid -> the Draft JSON rebuilt from the worksheet's sentences and citations."""
    drafts: dict = {}
    for row in read_jsonl(WORKSHEETS[scope]):
        if row.get("kind") != "sentence":
            continue
        cited = [c["passage_id"] for c in row.get("cited") or []]
        drafts.setdefault(row["qid"], []).append({"text": row["text"], "cited_ids": cited})
    return {qid: json.dumps({"sentences": s}, ensure_ascii=False) for qid, s in drafts.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", choices=["pilot", "microlog"], required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    import anthropic
    from archive_debugger import scopes
    from archive_debugger.api.app import clean_question
    from archive_debugger.generate.answer import compose
    from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool
    from archive_debugger.generate.llm import Draft
    from archive_debugger.retrieve import citation
    from archive_debugger.retrieve.search import Retriever

    resolved = scopes.resolve_scope(args.scope)
    active = None if resolved.inherit else resolved
    with scopes.activate(active):
        retriever = Retriever(Path(resolved.config_path))
        gcfg = load_generate_config(Path(resolved.config_path))
    model = gcfg["model"]
    price_in, price_out = PRICES[model]
    # The repo's .env key first, then the environment's: a stale shell export must not shadow it.
    from dotenv import dotenv_values
    client = anthropic.Anthropic(api_key=dotenv_values(".env").get("ANTHROPIC_API_KEY") or None, max_retries=5)

    def count(system, user) -> int:
        time.sleep(PAUSE_S)
        kwargs = {"model": model, "messages": [{"role": "user", "content": user}], "output_format": Draft}
        if system is not None:
            kwargs["system"] = system
        return client.messages.count_tokens(**kwargs).input_tokens

    empty_message = count(None, ".")
    drafts = worksheet_drafts(args.scope)
    rows = []
    for q in questions_for(args.scope):
        clean = clean_question(q["text"])
        _pool, hits = retrieve_pool(retriever, clean, build_filters(q["filters"]), gcfg["top_k"])
        recorder = RecordingLLM()
        compose(clean, hits, recorder, functools.partial(citation.verify_citations, retriever.conn),
                min_passages=gcfg["min_passages"])
        row = {"id": q["id"], "kind": q["kind"], "model_called": bool(recorder.calls), "passages_in_prompt": len(hits)}
        if recorder.calls:
            system, user = recorder.calls[0]
            row["input_tokens"] = count(system, user)
            row["prompt_chars"] = len(system) + len(user)
            if q["id"] in drafts:
                row["output_tokens_estimate"] = max(0, count(None, drafts[q["id"]]) - empty_message)
        rows.append(row)
        print(json.dumps(row), flush=True)

    called = [r for r in rows if r["model_called"]]
    inputs = [r["input_tokens"] for r in called]
    outputs = [r["output_tokens_estimate"] for r in called if "output_tokens_estimate" in r]
    out_median = statistics.median(outputs) if outputs else None

    def usd(tokens_in, tokens_out):
        return tokens_in * price_in / 1e6 + (tokens_out or 0) * price_out / 1e6

    summary = {
        "scope": args.scope, "model": model, "price_usd_per_mtok": {"input": price_in, "output": price_out},
        "questions": len(rows), "model_called": len(called), "gate_abstained_no_call": len(rows) - len(called),
        "input_tokens": {"min": min(inputs), "median": statistics.median(inputs), "mean": round(statistics.mean(inputs), 1),
                         "max": max(inputs)} if inputs else None,
        "output_tokens_estimate": {"n": len(outputs), "min": min(outputs), "median": out_median,
                                   "max": max(outputs)} if outputs else None,
        "usd_per_uncached_answer_median": round(usd(statistics.median(inputs), out_median), 5) if inputs else None,
        "usd_per_uncached_answer_max": round(usd(max(inputs), max(outputs) if outputs else 0), 5) if inputs else None,
        "max_tokens_cap": gcfg["max_tokens"],
        "usd_worst_case_at_max_tokens": round(usd(max(inputs), gcfg["max_tokens"]), 5) if inputs else None,
        "count_tokens_overhead_subtracted": empty_message,
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
