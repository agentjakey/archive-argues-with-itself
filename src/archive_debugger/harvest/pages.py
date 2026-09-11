"""Offline pack of page images (harvest layer: this is the only module besides the
corpus harvest that fetches from archive.org). For each (item_id, leaf_index) it
fetches the page thumbnail and the medium page image once into
data/cache/pages/<item_id>/n<leaf>_thumb.jpg and n<leaf>_medium.jpg, skipping files
already present. Sequential requests, a polite delay, a User-Agent with a contact.

The running API never calls this; it only serves files that exist (GET /pages/...).
scripts/offline_pack.py decides which pages to fetch (every cached answer's evidence
and every story's pins)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from archive_debugger.harvest.explore import user_agent
from archive_debugger.retrieve import citation

DEFAULT_DIR = Path("data/cache/pages")
KINDS = {"thumb": citation.page_thumb, "medium": citation.page_image}

Transport = Callable[[str, dict], bytes]   # (url, headers) -> body; raises on non-200


def default_transport(url: str, headers: dict) -> bytes:
    import requests  # harvest layer only

    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.content


def page_file(pages_dir: Path, item_id: str, leaf: int, kind: str) -> Path:
    return Path(pages_dir) / item_id / f"n{leaf}_{kind}.jpg"


def fetch_page_images(targets: Iterable[tuple[str, int]], pages_dir: Path = DEFAULT_DIR, *, contact: str,
                      transport: Optional[Transport] = None, sleeper: Callable[[float], None] = time.sleep,
                      delay: float = 0.5, log: Callable[[str], None] = print) -> dict:
    """Fetch thumb + medium for each target once. Returns counts."""
    transport = transport or default_transport
    headers = {"User-Agent": user_agent(contact)}
    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    for item_id, leaf in sorted(set(targets)):
        for kind, url_fn in KINDS.items():
            dest = page_file(pages_dir, item_id, leaf, kind)
            if dest.is_file() and dest.stat().st_size > 0:
                counts["skipped"] += 1
                continue
            url = url_fn(item_id, leaf)
            try:
                body = transport(url, headers)
            except Exception as exc:  # noqa: BLE001 - recorded, run continues
                counts["failed"] += 1
                log(f"failed {url}: {type(exc).__name__}: {exc}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            counts["fetched"] += 1
            if counts["fetched"] % 50 == 0:
                log(f"  fetched {counts['fetched']} images so far")
            sleeper(delay)
    return counts
