"""Refresh Gap Hunt's catalogue counts: 85 count-only searches of the Internet Archive's public search
API (the collection total, then every province, territory and the federal proxy by decade), one at a
time with a pause, under the project's user agent. Writes exhibit/decks/starter/catalogue_counts.json.
No item metadata or text is downloaded.

    python scripts/v2/exhibit_catalogue_counts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.exhibit import gaphunt  # noqa: E402

OUT = REPO / "exhibit" / "decks" / "starter" / "catalogue_counts.json"


def main() -> int:
    counts = gaphunt.fetch_catalogue_counts()
    OUT.write_text(json.dumps(counts, indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    print(f"total {counts['total']}; {len(counts['cells'])} cells -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
