"""Coverage view: what the corpus lexically holds for a question's salient terms,
by decade and by jurisdiction, under the active filters. Read-only over civic.db.

The term rule is the abstention gate's (generate.answer.salient_terms and its
stem / 5-character-prefix / year / decade coverage), expressed as FTS5 MATCH
expressions where FTS can express it: a prefix query for terms whose stem is at
least 5 characters, the singular and plural forms for shorter stems, the literal
year for 4-digit terms, and the ten years plus the literal token for a decade.
Counts are lexical matches, never relevance.

Lanes: the pilot window decades and "undated" always appear; dated items outside
the window fold into "pre-1960" and "post-2009" and appear only when the current
filters leave passages there."""
from __future__ import annotations

from typing import Optional

from archive_debugger.generate.answer import PREFIX, _DECADE, _stem, salient_terms
from archive_debugger.retrieve.filters import Filters, build_where

WINDOW_LANES = ["1960s", "1970s", "1980s", "1990s", "2000s"]
FIXED_LANES = WINDOW_LANES + ["undated"]
PRE, POST = "pre-1960", "post-2009"
_DECADE_SQL = "CASE WHEN i.dated = 1 THEN COALESCE(i.decade, 'undated') ELSE 'undated' END"
_JUR_SQL = "COALESCE(i.jurisdiction_norm, 'unknown')"


def fts_expression(term: str) -> str:
    """One FTS5 MATCH expression per salient term, mirroring the coverage rule."""
    if _DECADE.match(term):
        base = term[:3]
        return " OR ".join([f'"{base}{d}"' for d in range(10)] + [f'"{term}"'])
    if term.isdigit() and len(term) == 4:
        return f'"{term}"'
    stem = _stem(term)
    if len(stem) >= PREFIX:
        return f'"{stem[:PREFIX]}"*'          # prefix query: sanatoria / sanatorium / sanatoriums
    forms = sorted({stem, stem + "s", term})  # short stems: exact singular and plural
    return " OR ".join(f'"{f}"' for f in forms)


def lane_of(decade: str) -> str:
    """Fold a raw decade label into a display lane."""
    if decade in FIXED_LANES:
        return decade
    if _DECADE.match(decade):
        return PRE if int(decade[:4]) < 1960 else POST
    return "undated"


def lane_order(keys) -> list[str]:
    keys = set(keys)
    return [k for k in [PRE, *WINDOW_LANES, POST, "undated"] if k in keys]


def _empty_lane(lane: str) -> dict:
    return {"decade": lane, "items": 0, "passages": 0, "undated_passages": 0, "matched": 0, "terms": {}}


def coverage(conn, question: str, filters: Filters, *, doc_type_families: Optional[dict] = None) -> dict:
    where, params = build_where(filters, doc_type_families=doc_type_families)
    terms = salient_terms(question)

    by_decade: dict[str, dict] = {lane: _empty_lane(lane) for lane in FIXED_LANES}
    for d, items, passages, undated in conn.execute(
        f"SELECT {_DECADE_SQL} AS d, COUNT(DISTINCT i.item_id), COUNT(*), "
        f"SUM(CASE WHEN i.dated = 1 THEN 0 ELSE 1 END) "
        f"FROM passages p JOIN items i ON i.item_id = p.item_id WHERE 1 = 1{where} GROUP BY d",
        params,
    ):
        row = by_decade.setdefault(lane_of(d), _empty_lane(lane_of(d)))
        row["items"] += items          # items straddling two folded decades cannot occur: one decade per item
        row["passages"] += passages
        row["undated_passages"] += undated or 0

    by_jur: dict[str, dict] = {}
    for j, passages in conn.execute(
        f"SELECT {_JUR_SQL} AS j, COUNT(*) FROM passages p JOIN items i ON i.item_id = p.item_id "
        f"WHERE 1 = 1{where} GROUP BY j",
        params,
    ):
        by_jur[j] = {"jurisdiction": j, "passages": passages, "terms": {}}

    def counts(expr: str, group_sql: str, fold) -> dict[str, int]:
        out: dict[str, int] = {}
        for g, n in conn.execute(
            f"SELECT {group_sql} AS g, COUNT(*) FROM passages_fts f "
            f"JOIN passages p ON p.rowid = f.rowid JOIN items i ON i.item_id = p.item_id "
            f"WHERE passages_fts MATCH ?{where} GROUP BY g",
            [expr, *params],
        ):
            out[fold(g)] = out.get(fold(g), 0) + n
        return out

    for term in terms:
        expr = fts_expression(term)
        dec = counts(expr, _DECADE_SQL, lane_of)
        jur = counts(expr, _JUR_SQL, lambda j: j)
        for d, row in by_decade.items():
            row["terms"][term] = dec.get(d, 0)
        for j, row in by_jur.items():
            row["terms"][term] = jur.get(j, 0)
    if terms:
        any_expr = " OR ".join(f"({fts_expression(t)})" for t in terms)
        matched = counts(any_expr, _DECADE_SQL, lane_of)
        for d, row in by_decade.items():
            row["matched"] = matched.get(d, 0)

    return {
        "salient_terms": terms,
        "by_decade": [by_decade[d] for d in lane_order(by_decade.keys())],
        "by_jurisdiction": sorted(by_jur.values(), key=lambda r: (-r["passages"], r["jurisdiction"])),
    }
