"""Metadata filters compiled to SQL predicates. Pre-filter (candidate-set
restriction) on both arms; compose with AND.

doc_type families (Phase 13, config-driven): when a mapping is supplied and the
requested doc_type names a family or one of its members, the predicate matches
every member. Stored values are never rewritten."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Filters:
    period: Optional[str] = None          # '1980s' | 'pre-1960' | 'post-2009' | 'undated'
    jurisdiction: Optional[str] = None
    doc_type: Optional[str] = None
    min_ocr: float = 0.0
    # Catalogue year bounds (inclusive). Each one keeps only dated items: an undated item has no
    # catalogue year to compare, and a derived date never stands in for one here.
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    # "As of" a year: what the record held by then, so items catalogued in that year or before. The
    # same predicate as year_to; the engine also prefers the most recent of them when it ranks.
    as_of_year: Optional[int] = None
    issuer: Optional[str] = None          # exact issuer_norm (the catalogue's normalized issuer)
    # Documents a governance policy restricts from retrieval (governance.py). Set by the engine from
    # the register, never from a request, and applied to both arms before the search.
    exclude_items: tuple = ()


def period_predicate(period: str) -> tuple[str, list]:
    if period == "undated":
        return "i.dated = 0", []
    if period == "pre-1960":
        return "i.dated = 1 AND i.year < 1960", []
    if period == "post-2009":
        return "i.dated = 1 AND i.year > 2009", []
    if period.endswith("s") and period[:-1].isdigit():
        d = int(period[:-1])
        return "i.dated = 1 AND i.year BETWEEN ? AND ?", [d, d + 9]
    raise ValueError(f"unknown period: {period}")


def family_members(doc_type: str, families: Optional[dict]) -> list[str]:
    """Members of the family doc_type names or belongs to; [] when there is none."""
    for name, members in (families or {}).items():
        if doc_type == name or doc_type in members:
            return list(members)
    return []


def build_where(f: Filters, *, doc_type_families: Optional[dict] = None) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if f.period:
        c, p = period_predicate(f.period)
        clauses.append(c)
        params += p
    if f.jurisdiction:
        clauses.append("i.jurisdiction_norm = ?")
        params.append(f.jurisdiction)
    if f.doc_type:
        members = family_members(f.doc_type, doc_type_families)
        if members:
            clauses.append("i.doc_type_norm IN (" + ",".join("?" * len(members)) + ")")
            params += members
        else:
            clauses.append("i.doc_type_norm = ?")
            params.append(f.doc_type)
    if f.issuer:
        clauses.append("i.issuer_norm = ?")
        params.append(f.issuer)
    if f.year_from is not None:
        clauses.append("i.dated = 1 AND i.year >= ?")
        params.append(int(f.year_from))
    upper = [int(y) for y in (f.year_to, f.as_of_year) if y is not None]
    if upper:
        clauses.append("i.dated = 1 AND i.year <= ?")
        params.append(min(upper))
    if f.min_ocr and f.min_ocr > 0:
        clauses.append("CAST(p.ocr_quality AS REAL) >= ?")
        params.append(f.min_ocr)
    if f.exclude_items:
        clauses.append("i.item_id NOT IN (" + ",".join("?" * len(f.exclude_items)) + ")")
        params += list(f.exclude_items)
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params
