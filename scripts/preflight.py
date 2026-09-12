"""Preflight for the offline exhibit: one command that proves the festival laptop will
work with the network off. Checks, and prints a green/red line for each:

  1. /health responds ok (the local API is up).
  2. the answer cache has an entry for every seed question and every story question.
  3. every page image referenced by those cached answers and by the story pins is
     present under the pages dir (thumb and medium for each item/leaf).

Non-zero exit on any red, with the count and the ids of what is missing. Run it with
the network off, against the locally running API:

    python scripts/preflight.py                       # base http://127.0.0.1:8000
    python scripts/preflight.py http://127.0.0.1:8000

Only /health touches the network, and that is a call to the local server, not the
internet; nothing here reaches archive.org or the model.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

GREEN, RED = "OK  ", "FAIL"


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


def cache_keys(cache_db: Path) -> set:
    if not cache_db.exists():
        return set()
    conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    try:
        return {k for (k,) in conn.execute("SELECT key FROM answers")}
    finally:
        conn.close()


def cached_evidence_targets(cache_db: Path) -> set:
    """(item_id, leaf_index) for every evidence row of every cached answer."""
    out: set = set()
    if not cache_db.exists():
        return out
    conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    try:
        for (body,) in conn.execute("SELECT response_json FROM answers"):
            for row in json.loads(body).get("evidence", []):
                out.add((row["item_id"], int(row["leaf_index"])))
    finally:
        conn.close()
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


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.api.app import DEFAULT_CACHE, DEFAULT_PAGES, DEFAULT_STORIES, ENV_PAGES_DIR, answer_cache_key, load_stories
    from archive_debugger.api.cache import retrieval_fingerprint
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger.harvest.pages import page_file
    from archive_debugger.ingest.db import ENV_CACHE_PATH, env_path, resolve_db_path
    from archive_debugger.retrieve.config import load_retrieve_config

    base = (argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
    config = Path("config/pilot.toml")
    gcfg = load_generate_config(config)
    sha = retrieval_fingerprint(load_retrieve_config(config))
    cache_db = env_path(ENV_CACHE_PATH, DEFAULT_CACHE)
    pages_dir = env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    civic_db = resolve_db_path(config)
    seed = load_seed(Path("eval/seed_questions.jsonl"))
    stories = load_stories(DEFAULT_STORIES)

    reds: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        print(f"[{GREEN if ok else RED}] {label}" + (f"  {detail}" if detail else ""))
        if not ok:
            reds.append(label)

    # 1. health
    ok, detail = health_ok(base)
    check(ok, "/health responds ok", detail)

    # 2. answer cache covers every seed question and story question
    keys = cache_keys(cache_db)
    want = [("seed " + q["qid"], q["text"], q.get("filters") or {}) for q in seed]
    want += [("story " + s["id"], s["question"], s.get("filters") or {}) for s in stories]
    missing_cache = [name for name, text, filt in want
                     if answer_cache_key(gcfg, gcfg["provider"], gcfg["model"], text, filt, sha) not in keys]
    check(not missing_cache,
          f"answer cache covers all {len(want)} seed questions and stories",
          "" if not missing_cache else f"missing {len(missing_cache)}: {', '.join(missing_cache)}")

    # 3. page images present for every cached-evidence and story-pin (item, leaf)
    targets = cached_evidence_targets(cache_db)
    story_targets, missing_pins = set(), []
    for s in stories:
        t, miss = pin_targets(civic_db, s.get("pins", []))
        story_targets |= t
        missing_pins += [f"{s['id']}:{p}" for p in miss]
    targets |= story_targets
    missing_imgs = []
    for item, leaf in sorted(targets):
        for kind in ("thumb", "medium"):
            f = page_file(pages_dir, item, leaf, kind)
            if not (f.is_file() and f.stat().st_size > 0):
                missing_imgs.append(f"{item} n{leaf} {kind}")
    check(not missing_imgs,
          f"page images present for all {len(targets)} referenced pages ({pages_dir})",
          "" if not missing_imgs else f"missing {len(missing_imgs)}: {', '.join(missing_imgs[:20])}"
          + (" ..." if len(missing_imgs) > 20 else ""))
    if missing_pins:
        check(False, "story pins resolve in civic.db", f"unresolved: {', '.join(missing_pins)}")

    print()
    if reds:
        print(f"RED: {len(reds)} check(s) failed. Do not go on stage until green.")
        return 1
    print("GREEN: every check passed. Safe to run offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
