"""The Time Dial's evidence, gathered offline with the frozen retrieval (read-only, unchanged).

For each question the retriever runs once per decade with its own decade filter, so the pool holds
the best pages of every decade rather than only the decade the topic peaks in. A dial step exists
for every year in which a pool page was published: the step's answer is drafted from the pool pages
published by that year and no others. Around the steps, the dial shows each year's count of indexed
items that mention the question's terms, so a quiet year is a measured zero, and years outside the
collection's period are marked not indexed, never quiet."""
from __future__ import annotations

import sqlite3
from typing import Optional

from archive_debugger.exhibit import care as care_mod
from archive_debugger.exhibit import pages as pages_mod
from archive_debugger.exhibit.settings import CareRules

MAX_STEP_PAGES = 6


def gather_pool(retriever, conn: sqlite3.Connection, collection: str, question: dict, decades: list, *,
                per_decade: int, rules: CareRules, max_chars: int, top_k: int = 12) -> list:
    """Page records for the question's pool, oldest first, each with its retrieval rank. Pages on a
    care topic, undated pages and pages whose date is not verified are left out."""
    from archive_debugger.retrieve.filters import Filters
    pool, seen = [], set()
    for decade in decades:
        hits = retriever.search(question["en"], Filters(period=f"{decade}s", jurisdiction=question.get("jurisdiction")),
                                top_k=top_k)
        kept = 0
        for rank, h in enumerate(hits, 1):
            ref = pages_mod.page_ref(h["item_id"], h["leaf_index"])
            if ref in seen or h.get("year") is None:
                continue
            record = pages_mod.page_record(conn, collection, h["item_id"], h["leaf_index"],
                                           keep_quotes=[h.get("text") or ""], max_chars=max_chars)
            if record is None or not record["date_verified"]:
                continue
            if care_mod.care_flags([record["title"] or "", record["text"]], rules):
                continue
            seen.add(ref)
            record["retrieval"] = {"decade": decade, "rank": rank, "passage_id": h["passage_id"]}
            pool.append(record)
            kept += 1
            if kept >= per_decade:
                break
    pool.sort(key=lambda p: (p["catalogue_date"]["year"], p["retrieval"]["rank"]))
    return pool


def step_pages(pool: list, year: int) -> list:
    """The pages a step at `year` is drafted from: the pool pages published by then, at most
    MAX_STEP_PAGES, keeping the best-ranked page of each decade first and then the most recent."""
    by_then = [p for p in pool if p["catalogue_date"]["year"] <= year]
    if len(by_then) <= MAX_STEP_PAGES:
        return by_then
    best_per_decade = {}
    for p in by_then:
        d = p["retrieval"]["decade"]
        if d not in best_per_decade or p["retrieval"]["rank"] < best_per_decade[d]["retrieval"]["rank"]:
            best_per_decade[d] = p
    chosen = list(best_per_decade.values())
    for p in sorted(by_then, key=lambda p: -p["catalogue_date"]["year"]):
        if len(chosen) >= MAX_STEP_PAGES:
            break
        if p not in chosen:
            chosen.append(p)
    chosen = chosen[-MAX_STEP_PAGES:] if len(chosen) > MAX_STEP_PAGES else chosen
    return sorted(chosen, key=lambda p: (p["catalogue_date"]["year"], p["ref"]))


def step_years(pool: list) -> list:
    return sorted({p["catalogue_date"]["year"] for p in pool})


def year_counts(conn: sqlite3.Connection, terms: str, first: int, last: int, jurisdiction: Optional[str]) -> dict:
    """{year: number of indexed items with a passage matching the terms} for every year in the dial,
    zeros included."""
    sql = ("SELECT i.year AS year, COUNT(DISTINCT i.item_id) AS n FROM passages_fts f "
           "JOIN passages p ON p.rowid = f.rowid JOIN items i ON i.item_id = p.item_id "
           "WHERE passages_fts MATCH ? AND i.dated = 1 AND i.year BETWEEN ? AND ?")
    params: list = [terms, first, last]
    if jurisdiction:
        sql += " AND i.jurisdiction_norm = ?"
        params.append(jurisdiction)
    counts = {y: 0 for y in range(first, last + 1)}
    for r in conn.execute(sql + " GROUP BY i.year", params):
        counts[int(r["year"])] = int(r["n"])
    return counts


def dial_extra(counts: dict, period: tuple, first: int, last: int) -> dict:
    """Per-year states for the dial: not_indexed outside the collection's period, quiet where the
    count is zero, otherwise the count."""
    years = []
    for y in range(first, last + 1):
        if y < period[0] or y > period[1]:
            years.append({"year": y, "state": "not_indexed", "items": None})
        elif counts.get(y, 0) == 0:
            years.append({"year": y, "state": "quiet", "items": 0})
        else:
            years.append({"year": y, "state": "recorded", "items": counts[y]})
    return {"years": years, "collection_period": list(period)}
