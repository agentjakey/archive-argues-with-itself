"""Metadata filters compiled to SQL predicates. Pre-filter (candidate-set
restriction) on both arms; compose with AND."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Filters:
    period: Optional[str] = None          # '1980s' | 'pre-1960' | 'post-2009' | 'undated'
    jurisdiction: Optional[str] = None
    doc_type: Optional[str] = None
    min_ocr: float = 0.0


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


def build_where(f: Filters) -> tuple[str, list]:
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
        clauses.append("i.doc_type_norm = ?")
        params.append(f.doc_type)
    if f.min_ocr and f.min_ocr > 0:
        clauses.append("CAST(p.ocr_quality AS REAL) >= ?")
        params.append(f.min_ocr)
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params
