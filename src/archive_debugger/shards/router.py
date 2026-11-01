"""The router: which engines to wake for a question, and how to merge what they return.

choose() reads only the shards' static coverage files. A shard is eligible when its jurisdictions and
years can satisfy the question's filters and at least one query term occurs in it; eligible shards
are ranked by how much query-term evidence they hold (document frequency times the term's
collection-wide idf), and at most max_engines are woken. A shard left out is reported with why, so
an answer can say what it did not search ("not searched" is never "not in the archive").

merge() takes each woken engine's candidates. Dense scores are cosine similarities from one model, so
they compare directly across engines. BM25 does not: each engine's idf comes from its own passages.
So each candidate carries its query-term counts and length, and merge() recomputes BM25 with the
collection's N, document frequencies and average length summed over every coverage file. The two
rankings are fused by reciprocal rank (the engine's own rule, k = 60), and one model call is made on
the merged top passages."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from archive_debugger.shards.coverage import terms

RRF_K = 60
K1, B = 1.2, 0.75


@dataclass
class Choice:
    shard_id: str
    score: float
    reason: str


def _year_ok(cov: dict, jurisdiction: Optional[str], first: Optional[int], last: Optional[int], undated: bool) -> bool:
    for key, n in cov["years"].items():
        if n <= 0:
            continue
        place, _, year = key.partition("|")
        if jurisdiction and place != jurisdiction:
            continue
        if year == "undated":
            if undated or (first is None and last is None):
                return True
            continue
        y = int(year)
        if (first is None or y >= first) and (last is None or y <= last):
            return True
    return False


def global_stats(coverages: list) -> dict:
    n = sum(c["passages"] for c in coverages)
    tokens = sum(c["tokens"] for c in coverages)
    df: dict = {}
    for c in coverages:
        for t, k in c["df"].items():
            df[t] = df.get(t, 0) + k
    return {"N": n, "avgdl": tokens / n if n else 0.0, "df": df}


def idf(term: str, stats: dict) -> float:
    n, df = stats["N"], stats["df"].get(term, 0)
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def choose(question: str, coverages: list, *, jurisdiction: Optional[str] = None, first_year: Optional[int] = None,
           last_year: Optional[int] = None, undated: bool = False, max_engines: int = 3) -> tuple:
    """(chosen, left_out): lists of Choice. left_out says why each other shard was not woken."""
    q = list(dict.fromkeys(terms(question)))
    stats = global_stats(coverages)
    eligible, left = [], []
    for cov in coverages:
        if jurisdiction and jurisdiction not in cov["jurisdictions"]:
            left.append(Choice(cov["shard_id"], 0.0, "other jurisdictions"))
            continue
        if not _year_ok(cov, jurisdiction, first_year, last_year, undated):
            left.append(Choice(cov["shard_id"], 0.0, "no documents in the period"))
            continue
        score = sum(cov["df"].get(t, 0) * idf(t, stats) for t in q)
        if score <= 0:
            left.append(Choice(cov["shard_id"], 0.0, "none of the question's words occur in it"))
            continue
        eligible.append(Choice(cov["shard_id"], score / max(1, cov["passages"]) ** 0.5, "holds the question's words"))
    eligible.sort(key=lambda c: -c.score)
    for c in eligible[max_engines:]:
        left.append(Choice(c.shard_id, c.score, "ranked below the engines woken"))
    return eligible[:max_engines], left


def bm25(tf: dict, dl: int, q: list, stats: dict) -> float:
    avg = stats["avgdl"] or 1.0
    return sum(idf(t, stats) * tf.get(t, 0) * (K1 + 1) / (tf.get(t, 0) + K1 * (1 - B + B * dl / avg))
               for t in q if tf.get(t, 0))


def merge(question: str, hits_by_shard: dict, coverages: list, *, top_k: int = 10) -> list:
    """hits_by_shard: {shard_id: [{"passage_id", "dense", "tf": {term: count}, "dl", ...}]}. Returns the
    fused top_k, each with its shard, global BM25, dense score and both ranks."""
    q = list(dict.fromkeys(terms(question)))
    stats = global_stats(coverages)
    rows = []
    for shard_id, hits in hits_by_shard.items():
        for h in hits:
            rows.append({**h, "shard_id": shard_id, "bm25": bm25(h.get("tf") or {}, int(h.get("dl") or 0), q, stats)})
    by_bm25 = sorted((r for r in rows if r["bm25"] > 0), key=lambda r: (-r["bm25"], r["passage_id"]))
    by_dense = sorted((r for r in rows if r.get("dense") is not None), key=lambda r: (-r["dense"], r["passage_id"]))
    fused: dict = {}
    for rank, r in enumerate(by_bm25, 1):
        fused.setdefault(r["passage_id"], [r, 0.0, None, None])[1] += 1 / (RRF_K + rank)
        fused[r["passage_id"]][2] = rank
    for rank, r in enumerate(by_dense, 1):
        fused.setdefault(r["passage_id"], [r, 0.0, None, None])[1] += 1 / (RRF_K + rank)
        fused[r["passage_id"]][3] = rank
    ordered = sorted(fused.values(), key=lambda v: (-v[1], v[0]["passage_id"]))[:top_k]
    return [{**row, "rrf": round(score, 6), "bm25_rank": br, "dense_rank": dr} for row, score, br, dr in ordered]


def shard_hits(conn, question: str, *, dense_scores: Optional[dict] = None, limit: int = 40) -> list:
    """Candidates from one shard's corpus database for merge(): BM25 candidates from its full-text
    index, each with its query-term counts and length, plus a dense score when dense_scores
    ({passage_id: cosine}) has one. Used by the local engine in the bounded run; a deployed engine
    returns the same fields."""
    q = list(dict.fromkeys(terms(question)))
    if not q:
        return []
    match = " OR ".join('"' + t.replace('"', "") + '"' for t in q)
    rows = conn.execute("SELECT p.passage_id, p.text FROM passages_fts f JOIN passages p ON p.rowid = f.rowid "
                        "WHERE passages_fts MATCH ? ORDER BY f.rank LIMIT ?", (match, limit)).fetchall()
    out = []
    for pid, text in rows:
        words = terms(text)
        out.append({"passage_id": pid, "tf": {t: words.count(t) for t in q if t in words}, "dl": len(words),
                    "dense": (dense_scores or {}).get(pid)})
    return out
