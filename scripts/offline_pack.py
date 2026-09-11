"""Build the offline pack for the exhibit: page thumbnails and medium images for every
passage in every cached answer and every story pin, fetched once from archive.org into
data/cache/pages/ (or CIVIC_PAGES_DIR). The API serves them when present, so the app
shows real pages with no network. Also reports which story questions are NOT yet in
the answer cache (those would need the model, i.e. the network, when opened).

    python scripts/offline_pack.py [--contact you@example.com] [--dry-run]

Run scripts/warm_cache.py first so the cache holds every seed question."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tomllib
from pathlib import Path


def collect_targets(cache_db: Path, civic_db: Path, stories: list[dict]) -> tuple[set, list[str]]:
    targets: set[tuple[str, int]] = set()
    if cache_db.exists():
        conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
        for (body,) in conn.execute("SELECT response_json FROM answers"):
            for row in json.loads(body).get("evidence", []):
                targets.add((row["item_id"], int(row["leaf_index"])))
        conn.close()
    pins = [p for s in stories for p in s["pins"]]
    missing: list[str] = []
    if pins:
        conn = sqlite3.connect(f"file:{civic_db}?mode=ro", uri=True)
        found = {}
        for pid, item, leaf in conn.execute(
                f"SELECT passage_id, item_id, leaf_index FROM passages WHERE passage_id IN ({','.join('?' * len(pins))})", pins):
            found[pid] = (item, int(leaf))
        conn.close()
        for pid in pins:
            if pid in found:
                targets.add(found[pid])
            else:
                missing.append(pid)
    return targets, missing


def uncached_stories(cache_db: Path, stories: list[dict], config_path: Path) -> list[str]:
    from archive_debugger.api.app import answer_cache_key
    from archive_debugger.api.cache import retrieval_fingerprint
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger.retrieve.config import load_retrieve_config
    gcfg = load_generate_config(config_path)
    sha = retrieval_fingerprint(load_retrieve_config(config_path))
    if not cache_db.exists():
        return [s["id"] for s in stories]
    conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    keys = {k for (k,) in conn.execute("SELECT key FROM answers")}
    conn.close()
    out = []
    for s in stories:
        key = answer_cache_key(gcfg, gcfg["provider"], gcfg["model"], s["question"], s.get("filters") or {}, sha)
        if key not in keys:
            out.append(s["id"])
    return out


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.api.app import DEFAULT_CACHE, DEFAULT_PAGES, DEFAULT_STORIES, ENV_PAGES_DIR, load_stories
    from archive_debugger.harvest.pages import fetch_page_images
    from archive_debugger.ingest.db import ENV_CACHE_PATH, env_path, resolve_db_path

    p = argparse.ArgumentParser(description="Fetch page images for cached answers and stories into the offline pack.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--stories", default=DEFAULT_STORIES, type=Path)
    p.add_argument("--contact", default=None, help="contact for the User-Agent (default: [harvest].user_agent_contact)")
    p.add_argument("--delay", default=0.5, type=float)
    p.add_argument("--dry-run", action="store_true", help="list targets and uncached stories; fetch nothing")
    args = p.parse_args(argv)

    with args.config.open("rb") as fh:
        contact = args.contact or tomllib.load(fh).get("harvest", {}).get("user_agent_contact", "")
    cache_db = env_path(ENV_CACHE_PATH, DEFAULT_CACHE)
    pages_dir = env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    stories = load_stories(args.stories)
    targets, missing_pins = collect_targets(cache_db, resolve_db_path(args.config), stories)
    uncached = uncached_stories(cache_db, stories, args.config)

    print(f"answer cache: {cache_db} ({'present' if cache_db.exists() else 'absent'})")
    print(f"pages to hold: {len(targets)} (thumb + medium each) under {pages_dir}")
    if missing_pins:
        print(f"story pins not found in civic.db: {missing_pins}")
    if uncached:
        print(f"story questions NOT in the answer cache (would call the model when opened): {uncached}")
        print("  run scripts/warm_cache.py against the running API first")
    if args.dry_run:
        return 0
    if not contact:
        print("refusing to fetch from archive.org without a contact for the User-Agent: pass --contact "
              "or set [harvest].user_agent_contact in config/pilot.toml")
        return 2
    counts = fetch_page_images(sorted(targets), pages_dir, contact=contact, delay=args.delay)
    print(json.dumps(counts))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
