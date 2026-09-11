"""Offline pack: fetch once, skip existing, record failures; target collection from
the answer cache and story pins."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from archive_debugger.api.cache import AnswerCache
from archive_debugger.harvest import pages
from archive_debugger.ingest import db


def test_fetch_page_images_once_and_skip_existing(tmp_path):
    calls: list[str] = []

    def transport(url, headers):
        calls.append(url)
        assert "contact: me@example.com" in headers["User-Agent"]
        if "bad" in url:
            raise RuntimeError("404")
        return b"jpeg-bytes"

    slept: list[float] = []
    counts = pages.fetch_page_images([("itemA", 3), ("itemA", 3), ("bad", 1)], tmp_path, contact="me@example.com",
                                     transport=transport, sleeper=slept.append, delay=0.1, log=lambda _m: None)
    assert counts == {"fetched": 2, "skipped": 0, "failed": 2}
    assert (tmp_path / "itemA" / "n3_thumb.jpg").read_bytes() == b"jpeg-bytes"
    assert (tmp_path / "itemA" / "n3_medium.jpg").exists()
    assert sorted(calls) == sorted([
        "https://archive.org/download/itemA/page/n3_thumb.jpg", "https://archive.org/download/itemA/page/n3_medium.jpg",
        "https://archive.org/download/bad/page/n1_thumb.jpg", "https://archive.org/download/bad/page/n1_medium.jpg"])
    assert slept == [0.1, 0.1]                                                       # polite delay after each fetch
    again = pages.fetch_page_images([("itemA", 3)], tmp_path, contact="me@example.com",
                                    transport=transport, sleeper=slept.append, log=lambda _m: None)
    assert again == {"fetched": 0, "skipped": 2, "failed": 0}                        # idempotent


def test_collect_targets_from_cache_and_stories(tmp_path):
    spec = importlib.util.spec_from_file_location("offline_pack", Path("scripts/offline_pack.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cache = AnswerCache(tmp_path / "answers.db")
    cache.put("k1", {"answer": {}, "evidence": [{"item_id": "x", "leaf_index": 4}, {"item_id": "y", "leaf_index": 0}]})
    cache.close()
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    conn.execute("INSERT INTO items (item_id, title) VALUES ('z', 'z')")
    conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, has_text) VALUES ('z#7', 'z', 7, 1)")
    conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, text) VALUES ('z#7:0', 'z', 'z#7', 7, 't')")
    conn.commit()
    conn.close()
    stories = [{"id": "s", "question": "q", "pins": ["z#7:0", "nope#1:0"]}]
    targets, missing = mod.collect_targets(tmp_path / "answers.db", civ, stories)
    assert targets == {("x", 4), ("y", 0), ("z", 7)} and missing == ["nope#1:0"]
