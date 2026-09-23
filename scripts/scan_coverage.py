"""Offline-scan coverage audit (read-only, offline): does the local page-image pack
hold a real JPEG for every citation the exhibit can surface with the network off?

Surfaceable citations come from two places, and the exhibit renders their page images
(thumb in the evidence trail and cards, medium in the compare view and drawer):

  - the golden set: every evidence row of every cached answer (data/cache/answers.db);
  - the curated stories and the compare view: the two pinned passages of each story
    in config/stories.json (the compare pins are the story pins).

For each referenced page it checks the thumb and the medium image under the pages dir
and classifies each as ok, missing, or broken (present but empty or not a JPEG). It
prints a coverage percentage, the counts, and the exact list of what is missing or
broken so scripts/offline_pack.py can fetch it. Exits non-zero unless coverage is 100%.

    python scripts/scan_coverage.py

Fetches nothing and reaches no network; extend the pack with scripts/offline_pack.py
(network on) and re-run until this is 100%.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

JPEG_MAGIC = b"\xff\xd8\xff"


def image_state(path: Path) -> str:
    """'ok', 'missing', or 'broken' (present but empty or not a JPEG)."""
    if not path.is_file():
        return "missing"
    try:
        if path.stat().st_size == 0:
            return "broken"
        with path.open("rb") as fh:
            return "ok" if fh.read(3) == JPEG_MAGIC else "broken"
    except OSError:
        return "broken"


def cached_evidence(cache_db: Path) -> dict:
    """(item_id, leaf) -> set of source labels, from every cached answer's evidence."""
    out: dict = defaultdict(set)
    if not cache_db.exists():
        return out
    conn = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT response_json FROM answers").fetchall()
    finally:
        conn.close()
    for (body,) in rows:
        for row in json.loads(body).get("evidence", []):
            out[(row["item_id"], int(row["leaf_index"]))].add("cached-answer")
    return out


def story_pins(civic_db: Path, stories: list[dict]) -> tuple[dict, list[str]]:
    """(item_id, leaf) -> set of story labels, plus any pin not found in civic.db."""
    out: dict = defaultdict(set)
    pins = [(s["id"], p) for s in stories for p in s.get("pins", [])]
    if not pins:
        return out, []
    ids = [p for _sid, p in pins]
    conn = sqlite3.connect(f"file:{civic_db}?mode=ro", uri=True)
    try:
        found = {pid: (item, int(leaf)) for pid, item, leaf in conn.execute(
            f"SELECT passage_id, item_id, leaf_index FROM passages WHERE passage_id IN ({','.join('?' * len(ids))})", ids)}
    finally:
        conn.close()
    missing = []
    for sid, pid in pins:
        if pid in found:
            out[found[pid]].add(f"story:{sid}")
        else:
            missing.append(f"{sid}:{pid}")
    return out, missing


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.api.app import DEFAULT_PAGES, ENV_PAGES_DIR, load_stories, offline_scopes
    from archive_debugger.harvest.pages import page_file
    from archive_debugger.ingest.db import env_path

    pages_dir = env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    served = offline_scopes()   # pilot, plus any built scope present (e.g. microlog); shared pack

    # (item,leaf) -> {"scope:source"} across every served scope; the pack is one shared, item-id-keyed
    # dir, so both scopes' pages coexist without collision (item ids are distinct).
    refs: dict = defaultdict(set)
    missing_pins: list[str] = []
    print(f"pages dir: {pages_dir} ({'present' if Path(pages_dir).is_dir() else 'ABSENT'})")
    print(f"scopes covered offline: {', '.join(s['name'] for s in served)}")
    for s in served:
        cache_db = Path(s["cache_db"])
        civic_db = Path(s["civic_db"])
        stories = load_stories(s["stories"])
        ev = cached_evidence(cache_db)
        pins, miss = story_pins(civic_db, stories)
        for target, labels in ev.items():
            refs[target] |= {f"{s['name']}:{lab}" for lab in labels}
        for target, labels in pins.items():
            refs[target] |= {f"{s['name']}:{lab}" for lab in labels}
        missing_pins += [f"{s['name']}:{m}" for m in miss]
        print(f"  [{s['name']}] answer cache {'present' if cache_db.exists() else 'ABSENT'} "
              f"({len(ev)} answer pages); stories {len(stories)} ({len(pins)} pin pages)")
    print(f"surfaceable pages: {len(refs)} (thumb + medium = {2 * len(refs)} images)")
    if missing_pins:
        print(f"UNRESOLVED story pins (not in civic.db): {', '.join(missing_pins)}")

    counts = {"ok": 0, "missing": 0, "broken": 0}
    bad: list[str] = []
    for (item, leaf) in sorted(refs):
        for kind in ("thumb", "medium"):
            state = image_state(page_file(pages_dir, item, leaf, kind))
            counts[state] += 1
            if state != "ok":
                bad.append(f"{state:7} {item} n{leaf} {kind}  [{', '.join(sorted(refs[(item, leaf)]))}]")

    total = 2 * len(refs)
    pct = 100.0 * counts["ok"] / total if total else 100.0
    print()
    print(f"coverage: {counts['ok']}/{total} images = {pct:.1f}%  "
          f"(missing {counts['missing']}, broken {counts['broken']})")
    if bad:
        print("\nnot yet covered (run scripts/offline_pack.py to fetch):")
        for line in bad:
            print(f"  {line}")

    ok = not bad and not missing_pins
    print()
    print("GREEN: every surfaceable citation resolves to a local scan." if ok
          else "RED: some citations cannot render offline. Extend the pack and re-run.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
