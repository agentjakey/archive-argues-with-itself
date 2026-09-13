"""Preflight for the offline exhibit: one command that proves the festival laptop will
work with the network off. Prints a green/red line for each check and exits non-zero
on any red, so it is the ship gate: do not go on stage until it is green.

Checks, in order:

  1. civic.db and vectors.db exist and are non-empty files (the paths .env resolves).
  2. /health responds ok (the local API is up and has a corpus).
  3. the answer cache has an entry for every seed question and every story question,
     under the current model, prompt, retrieval config and index (the cache key).
  4. every page image referenced by those cached answers and by the story pins is
     present AND a real JPEG (thumb and medium for each item/leaf); a zero-byte or
     non-JPEG file is reported as broken, not just missing.
  5. the retrieval stack actually runs with the network off (this catches a
     vectors.db that is present but whose sqlite-vec extension will not load), every
     question returns enough passages, and every question the exhibit answers still
     clears the frozen abstention gate. Read-only: this constructs its own Retriever,
     runs retrieve + the frozen coverage/thinness rule, and writes nothing. It never
     re-scores or edits any published number (N5).
  6. every story/compare pin resolves in civic.db and expands through the same
     Retriever.lookup path the /stories endpoint uses, so the compare view renders.

Run it with the network off, against the locally running API:

    python scripts/preflight.py                       # base http://127.0.0.1:8000
    python scripts/preflight.py http://127.0.0.1:8000

Only /health touches the network, and that is a call to the local server, not the
internet; nothing here reaches archive.org or the model. Safe to run while the API
is up (it opens its own read-only handles).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

GREEN, RED = "OK  ", "FAIL"
JPEG_MAGIC = b"\xff\xd8\xff"


def load_seed(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def health_ok(base: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/health", timeout=30) as r:
            h = json.loads(r.read().decode("utf-8"))
        corpus = h.get("corpus", {})
        return (h.get("status") == "ok" and corpus.get("items", 0) > 0,
                f"status={h.get('status')}, items={corpus.get('items')}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc} (is the local API running?)"


def cache_responses(cache_db: Path) -> dict:
    """key -> parsed cached response, for every row of the answer cache."""
    out: dict = {}
    if not cache_db.exists():
        return out
    conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    try:
        for key, body in conn.execute("SELECT key, response_json FROM answers"):
            out[key] = json.loads(body)
    finally:
        conn.close()
    return out


def evidence_targets(responses: dict) -> set:
    """(item_id, leaf_index) for every evidence row of every cached answer."""
    out: set = set()
    for resp in responses.values():
        for row in resp.get("evidence", []):
            out.add((row["item_id"], int(row["leaf_index"])))
    return out


def pin_targets(civic_db: Path, pins: list[str]) -> tuple[set, list[str]]:
    if not pins:
        return set(), []
    conn = sqlite3.connect(f"file:{civic_db}?mode=ro", uri=True)
    try:
        found = {pid: (item, int(leaf)) for pid, item, leaf in conn.execute(
            f"SELECT passage_id, item_id, leaf_index FROM passages WHERE passage_id IN ({','.join('?' * len(pins))})", pins)}
    finally:
        conn.close()
    return {found[p] for p in pins if p in found}, [p for p in pins if p not in found]


def image_state(path: Path) -> str:
    """'ok', 'missing', or 'broken' (present but empty or not a JPEG)."""
    if not path.is_file():
        return "missing"
    try:
        if path.stat().st_size == 0:
            return "broken"
        with path.open("rb") as fh:
            head = fh.read(3)
        return "ok" if head == JPEG_MAGIC else "broken"
    except OSError:
        return "broken"


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.api.app import (DEFAULT_CACHE, DEFAULT_PAGES, DEFAULT_STORIES, ENV_PAGES_DIR,
                                          answer_cache_key, load_stories)
    from archive_debugger.api.cache import retrieval_fingerprint
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger.harvest.pages import page_file
    from archive_debugger.ingest.db import ENV_CACHE_PATH, env_path, resolve_db_path
    from archive_debugger.retrieve.config import load_retrieve_config

    base = (argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
    config = Path("config/pilot.toml")
    gcfg = load_generate_config(config)
    rcfg = load_retrieve_config(config)
    min_passages = gcfg["min_passages"]
    cache_db = env_path(ENV_CACHE_PATH, DEFAULT_CACHE)
    pages_dir = env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    civic_db = Path(resolve_db_path(config))
    index_db = Path(rcfg.index_path)
    seed = load_seed(Path("eval/seed_questions.jsonl"))
    stories = load_stories(DEFAULT_STORIES)

    reds: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        print(f"[{GREEN if ok else RED}] {label}" + (f"  {detail}" if detail else ""))
        if not ok:
            reds.append(label)

    # 1. data files exist and are non-empty
    def file_ok(p: Path) -> bool:
        return p.is_file() and p.stat().st_size > 0

    data_ok = file_ok(civic_db) and file_ok(index_db)
    check(data_ok, "civic.db and vectors.db exist and are non-empty",
          f"civic.db={'ok' if file_ok(civic_db) else 'MISSING'} ({civic_db}); "
          f"vectors.db={'ok' if file_ok(index_db) else 'MISSING'} ({index_db})")

    # 2. health
    ok, detail = health_ok(base)
    check(ok, "/health responds ok", detail)

    # 3. answer cache covers every seed question and story question
    responses = cache_responses(cache_db)
    keys = set(responses)
    # (label, text, filters, cache_key) for each exhibit question
    want = []
    for q in seed:
        k = answer_cache_key(gcfg, gcfg["provider"], gcfg["model"], q["text"], q.get("filters") or {},
                             retrieval_fingerprint(rcfg))
        want.append(("seed " + q["qid"], q["text"], q.get("filters") or {}, k))
    for s in stories:
        k = answer_cache_key(gcfg, gcfg["provider"], gcfg["model"], s["question"], s.get("filters") or {},
                             retrieval_fingerprint(rcfg))
        want.append(("story " + s["id"], s["question"], s.get("filters") or {}, k))
    missing_cache = [name for name, _text, _filt, k in want if k not in keys]
    check(not missing_cache,
          f"answer cache covers all {len(want)} seed questions and stories",
          "" if not missing_cache else f"missing {len(missing_cache)}: {', '.join(missing_cache)}")

    # 4. page images present and valid for every cached-evidence and story-pin (item, leaf)
    targets = evidence_targets(responses)
    story_targets, missing_pins = set(), []
    for s in stories:
        t, miss = pin_targets(civic_db, s.get("pins", []))
        story_targets |= t
        missing_pins += [f"{s['id']}:{p}" for p in miss]
    targets |= story_targets
    missing_imgs, broken_imgs = [], []
    for item, leaf in sorted(targets):
        for kind in ("thumb", "medium"):
            state = image_state(page_file(pages_dir, item, leaf, kind))
            if state == "missing":
                missing_imgs.append(f"{item} n{leaf} {kind}")
            elif state == "broken":
                broken_imgs.append(f"{item} n{leaf} {kind}")
    bad = missing_imgs + broken_imgs
    detail = ""
    if bad:
        detail = f"{len(missing_imgs)} missing, {len(broken_imgs)} broken: {', '.join(bad[:20])}" \
                 + (" ..." if len(bad) > 20 else "")
    check(not bad, f"page images present and valid for all {len(targets)} referenced pages ({pages_dir})", detail)
    if missing_pins:
        check(False, "story pins resolve in civic.db", f"unresolved: {', '.join(missing_pins)}")

    # 5 and 6 need a live Retriever. Skip cleanly if the data files are missing.
    if not data_ok:
        check(False, "retrieval stack runs offline", "skipped: civic.db or vectors.db missing")
        print()
        print(f"RED: {len(reds)} check(s) failed. Do not go on stage until green.")
        return 1

    retriever = None
    try:
        try:
            from archive_debugger.generate.answer import coverage_of, is_thin
            from archive_debugger.generate.cli import build_filters, retrieve_pool
            from archive_debugger.retrieve.search import Retriever
            retriever = Retriever(str(config))
        except Exception as exc:  # noqa: BLE001 - a retrieval stack that will not load is a red, not a crash
            check(False, "retrieval stack runs offline", f"{type(exc).__name__}: {exc}")
            retriever = None

        # 5. retrieval returns enough passages, and answered questions clear the gate
        if retriever is not None:
            thin_retrieval, gate_blocks = [], []
            n_answered = n_abstain = 0
            for name, text, filt, k in want:
                if k not in keys:
                    continue  # already flagged in check 3
                cached_abstained = bool(responses[k].get("answer", {}).get("abstained"))
                try:
                    _pool, hits = retrieve_pool(retriever, text, build_filters(filt), gcfg["top_k"])
                    cov = coverage_of(text, hits)
                    would_abstain = is_thin(cov, min_passages=min_passages)
                except Exception as exc:  # noqa: BLE001
                    gate_blocks.append(f"{name} (retrieval error: {type(exc).__name__})")
                    continue
                if cached_abstained:
                    n_abstain += 1
                    continue  # a designed abstention: enough-passages/gate not required
                n_answered += 1
                if cov.n_passages < min_passages:
                    thin_retrieval.append(f"{name} ({cov.n_passages}<{min_passages})")
                if would_abstain:
                    gate_blocks.append(f"{name} (uncovered: {', '.join(cov.uncovered_terms) or 'floor'})")
            problems = thin_retrieval + gate_blocks
            check(not problems,
                  f"retrieval runs offline; all {n_answered} answered questions clear the gate "
                  f"({n_abstain} abstain by design)",
                  "" if not problems else "; ".join(problems))

        # 6. story/compare pins expand through the same path /stories uses
        if retriever is not None:
            all_pins = [p for s in stories for p in s.get("pins", [])]
            try:
                retriever.lookup(all_pins)
                check(True, f"all {len(all_pins)} story/compare pins expand for the compare view")
            except LookupError as exc:
                check(False, "story/compare pins expand for the compare view", f"{type(exc).__name__}: {exc}")
    finally:
        if retriever is not None:
            retriever.close()

    print()
    if reds:
        print(f"RED: {len(reds)} check(s) failed. Do not go on stage until green.")
        return 1
    print("GREEN: every check passed. Safe to run offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
