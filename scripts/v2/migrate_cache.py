"""Move the curated rows of an old answer cache (format v1) to the content-addressed format (v2).

Only seed questions and story questions move. Every other row is a visitor's question; those rows
are never copied, printed or inspected beyond the fields this matching needs, and they stay in
the old file until it is deleted with the Railway volume (docs/PRIVACY.md).

A v1 row's key cannot be recomputed (it hashed file paths, sizes and mtimes that no longer exist),
and a row does not hold its question. So each curated question is matched by what it retrieves:
the script runs the scope's real retrieval for the question and its filters against the canonical
data, and a stored row matches when its evidence holds exactly the same pool of passages with the
same prefix shown to the model, and its generation settings are the ones the current context
uses (provider, model, prompt hash, top_k, temperature), and the salient terms in its stored coverage
block are the curated question's. When several rows match one question the
newest is taken. The stored answer text is copied unchanged; date methods and care flags are
computed for it exactly as the server does on serve.

Prints totals and curated question ids only. Writes the v2 table into --out (a new file, or the
same file as --old: the v1 table is not touched).

    CIVIC_DB_PATH=... CIVIC_INDEX_PATH=... python scripts/v2/migrate_cache.py --scope pilot \
        --old data/cache/answers.db --out data/cache/answers.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
import sys
from pathlib import Path

from archive_debugger import editorial, flags, scopes
from archive_debugger.api import app as app_mod
from archive_debugger.api import cache as answer_cache
from archive_debugger.eval.questions import load_seed
from archive_debugger.generate.answer import generation_meta, salient_terms
from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool, sent_temperature
from archive_debugger.retrieve.search import Retriever

def curated_questions(scope: str) -> list[dict]:
    """Seed and story questions of a scope (files named by its registry entry): label, question
    text, filters."""
    from archive_debugger import release_files
    seed_file, story_file = release_files.curated_files(scope)
    out = []
    if seed_file is not None and seed_file.exists():
        for q in load_seed(seed_file):
            out.append({"label": f"seed:{q['qid']}", "question": q["text"], "filters": q.get("filters") or {}})
    for s in editorial.load_stories(story_file) if story_file is not None else []:
        out.append({"label": f"story:{s['id']}", "question": editorial.asked_question(s), "filters": s.get("filters") or {}})
    return out


def signature_of_rows(evidence: list[dict]) -> tuple:
    pool = frozenset(row["passage_id"] for row in evidence)
    prompt = frozenset(row["passage_id"] for row in evidence if row.get("in_prompt"))
    return pool, prompt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", required=True, help="a scope in config/scopes.toml")
    parser.add_argument("--old", required=True, help="the v1 answers.db")
    parser.add_argument("--out", required=True, help="where the v2 table is written")
    args = parser.parse_args(argv)

    resolved = scopes.resolve_scope(args.scope)
    active = None if resolved.inherit else resolved
    cfg_path = Path(resolved.config_path)
    with scopes.activate(active):
        retriever = Retriever(cfg_path)
        gcfg = load_generate_config(cfg_path)
    kind, model_id = gcfg["provider"], gcfg["model"]
    temp = sent_temperature(kind, gcfg)
    want_gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                               max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
    context = app_mod.cache_context(args.scope, answer_cache.canonical_data_sha256(args.scope),
                                    answer_cache.retrieve_settings(retriever.cfg), gcfg, kind, model_id)

    # What each curated question retrieves today, against the canonical data.
    wanted = {}
    for q in curated_questions(args.scope):
        clean = app_mod.clean_question(q["question"])
        pool_rows, hits = retrieve_pool(retriever, clean, build_filters(q["filters"]), gcfg["top_k"])
        pool = frozenset(h["passage_id"] for h in pool_rows)
        prompt = frozenset(h["passage_id"] for h in hits)
        wanted[(pool, prompt)] = wanted.get((pool, prompt), []) + [q]

    old = sqlite3.connect(f"file:{Path(args.old).resolve().as_posix()}?mode=ro", uri=True)
    totals = {"rows": 0, "generation_mismatch": 0, "matched_rows": 0, "unmatched_rows": 0}
    best: dict = {}
    for _key, body, created in old.execute("SELECT key, response_json, created_at FROM answers"):
        totals["rows"] += 1
        response = json.loads(body)
        generation = (response.get("answer") or {}).get("generation") or {}
        if any(generation.get(k) != want_gen[k] for k in ("provider", "model", "prompt_sha256", "top_k", "temperature")):
            totals["generation_mismatch"] += 1
            continue
        # Same pool and prompt prefix, and the same salient terms as the curated question (the
        # stored coverage block records them), so a different question that happened to retrieve
        # the same passages is never taken for a curated one.
        stored_terms = ((response.get("answer") or {}).get("coverage") or {}).get("salient_terms")
        matches = [q for q in wanted.get(signature_of_rows(response.get("evidence") or []), [])
                   if stored_terms == salient_terms(app_mod.clean_question(q["question"]))]
        if not matches:
            totals["unmatched_rows"] += 1
            continue
        totals["matched_rows"] += 1
        for q in matches:
            if q["label"] not in best or created > best[q["label"]][1]:
                best[q["label"]] = (response, created, q)
    old.close()

    store = answer_cache.LocalCache(Path(args.out))
    moved = []
    for label, (response, created, q) in sorted(best.items()):
        clean = app_mod.clean_question(q["question"])
        app_mod._attach_date_method(retriever.conn, response["evidence"])
        answer = response["answer"]
        response["flagged"] = flags.detect(response["evidence"], question=clean,
                                           answer_text=answer.get("text")) if not answer.get("abstained") else None
        answer.pop("cached", None)
        record = answer_cache.make_record(
            key=app_mod.answer_cache_key(context, q["question"], q["filters"]), scope=args.scope, context=context,
            response=response, extras_version=app_mod.EXTRAS_VERSION,
            curated_question=answer_cache.normalize_question(q["question"]),
            now=datetime.fromisoformat(created))
        store.put(record)
        moved.append(label)
    store.close()
    retriever.close()

    missing = sorted(q["label"] for qs in wanted.values() for q in qs if q["label"] not in best)
    print(json.dumps({"scope": args.scope, "context": context, **totals,
                      "curated_questions": sum(len(qs) for qs in wanted.values()),
                      "curated_moved": len(moved), "curated_missing": missing}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
