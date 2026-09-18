"""by_period for the thematic timeline (P-EXP-13): real per-period document counts, undated as its
own bucket, buckets identical to ingest.normalize.period_of, and the undated bucket single-sourced
with the undated item count the sources view reports. Uses a tiny in-memory items table; no real
corpus or network."""

from __future__ import annotations

import sqlite3
from collections import Counter

from archive_debugger.api.app import _period_distribution
from archive_debugger.ingest.normalize import period_of


def _items_db(rows) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE items (item_id TEXT PRIMARY KEY, year INTEGER, dated INTEGER)")
    conn.executemany("INSERT INTO items (item_id, year, dated) VALUES (?,?,?)", rows)
    conn.commit()
    return conn


def test_by_period_counts_match_period_of_buckets():
    # A spread across pre-1960, several decades (nothing in the 1980s), post-2009, and undated.
    rows = [
        ("a", 1955, 1),   # pre-1960
        ("b", 1968, 1),   # 1960s
        ("c", 1972, 1),   # 1970s
        ("d", 1979, 1),   # 1970s
        ("e", 1995, 1),   # 1990s
        ("f", 2003, 1),   # 2000s
        ("g", 2014, 1),   # post-2009
        ("h", None, 0),   # undated
        ("i", None, 0),   # undated
    ]
    dist = _period_distribution(_items_db(rows))
    assert dist == {
        "pre-1960": 1,
        "1960s": 1,
        "1970s": 2,
        "1990s": 1,
        "2000s": 1,
        "post-2009": 1,
        "undated": 2,
    }
    # The SQL buckets equal ingest.normalize.period_of for every row: one period definition, so the
    # histogram can never drift from the retriever's own period filter.
    assert dist == dict(Counter(period_of(y, d) for _, y, d in rows))
    # The 1980s gap is a real absence, not a zero row here; the frontend fills interior gaps.
    assert "1980s" not in dist


def test_undated_bucket_equals_the_undated_item_count():
    # by_period['undated'] must equal the dated=0 count the sources view reports as undated.items,
    # so the timeline's undated bar and the sources view's undated share share one basis.
    rows = [("a", 1990, 1), ("b", None, 0), ("c", None, 0), ("d", None, 0)]
    conn = _items_db(rows)
    dist = _period_distribution(conn)
    undated_items = conn.execute(
        "SELECT COUNT(*) FROM items WHERE dated = 0 OR dated IS NULL").fetchone()[0]
    assert dist["undated"] == undated_items == 3


def test_decade_only_corpus_has_no_out_of_window_buckets():
    # No fabricated pre-1960 or post-2009 bucket when the corpus holds none.
    rows = [("a", 1988, 1), ("b", 2001, 1)]
    dist = _period_distribution(_items_db(rows))
    assert dist == {"1980s": 1, "2000s": 1}
    assert "pre-1960" not in dist and "post-2009" not in dist and "undated" not in dist
