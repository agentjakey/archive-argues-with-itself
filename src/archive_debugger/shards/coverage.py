"""A shard's static coverage file, computed when the shard is built and published beside it, so the
router can choose engines without waking any:

  shard_id, jurisdictions, years: {"<jurisdiction>|<year or undated>": documents}
  passages, tokens                 for collection-wide BM25 (N and average length)
  df                               {term: passages containing it}, every term in two or more passages

Terms are the BM25 leg's: lower-cased words with the stopwords removed (archive_debugger.stopwords,
the frozen list), so document frequencies here add up to the collection's."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter

from archive_debugger.stopwords import STOPWORDS

WORD = re.compile(r"[^\W_]+", re.UNICODE)
FORMAT = 1


def terms(text: str) -> list:
    return [w for w in (m.lower() for m in WORD.findall(text or "")) if w not in STOPWORDS]


def compute(conn: sqlite3.Connection, shard_id: str, *, min_df: int = 2) -> dict:
    df: Counter = Counter()
    passages = tokens = 0
    for (text,) in conn.execute("SELECT text FROM passages"):
        words = terms(text)
        passages += 1
        tokens += len(words)
        df.update(set(words))
    years: Counter = Counter()
    jurisdictions = set()
    for place, year, dated in conn.execute("SELECT COALESCE(jurisdiction_norm, 'unknown'), year, dated FROM items"):
        jurisdictions.add(place)
        years[f"{place}|{year if dated and year is not None else 'undated'}"] += 1
    return {"format": FORMAT, "shard_id": shard_id, "jurisdictions": sorted(jurisdictions), "years": dict(years),
            "passages": passages, "tokens": tokens, "df": {t: n for t, n in df.items() if n >= min_df}}
