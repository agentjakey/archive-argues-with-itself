"""Compose a cited answer or abstain. Two abstentions, both decided by code:
(1) thin FTS-matched evidence before any model call; (2) no sentence survived the
3-check citation verifier. Failing or uncited sentences are dropped and listed."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from archive_debugger.generate.llm import LLM
from archive_debugger.generate.prompt import SYSTEM, build_user_prompt

ABSTAIN_THIN = (
    "the record here is thin: {n_fts_items} items and {n_fts_passages} passages match the "
    "question's terms ({n_undated} of {n_passages} retrieved passages are undated)"
)
ABSTAIN_UNVERIFIED = "no claim in the retrieved passages survived citation verification"
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_PAGE = re.compile(r"\b(?:p\.|page)\s*(\d+)\b", re.IGNORECASE)


@dataclass
class Coverage:
    n_items: int            # full retrieved set (for the UI)
    n_passages: int
    n_undated: int
    periods: dict
    jurisdictions: dict
    n_fts_items: int        # FTS-matched subset (drives thinness)
    n_fts_passages: int


@dataclass
class Answer:
    text: str
    sentences: list[dict]
    verified_citations: list[dict]
    unsupported: list[dict]
    abstained: bool
    coverage: Coverage
    abstention_text: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def coverage_of(hits: list[dict]) -> Coverage:
    fts = [h for h in hits if h.get("bm25_rank") is not None]
    return Coverage(
        n_items=len({h["item_id"] for h in hits}),
        n_passages=len(hits),
        n_undated=sum(1 for h in hits if not h.get("dated")),
        periods=dict(Counter(str(h.get("decade") or "undated") for h in hits)),
        jurisdictions=dict(Counter(str(h.get("jurisdiction") or "unknown") for h in hits)),
        n_fts_items=len({h["item_id"] for h in fts}),
        n_fts_passages=len(fts),
    )


def is_thin(cov: Coverage, *, min_items: int, min_passages: int) -> bool:
    return cov.n_fts_items < min_items or cov.n_fts_passages < min_passages


def _citation_dict(h: dict) -> dict:
    return {"passage_id": h["passage_id"], "item_id": h["item_id"], "leaf_index": h["leaf_index"],
            "printed_page": h.get("printed_page"), "deep_link": h["page_deep_link"]}


def _leaks_facts(text: str, cited: list[dict]) -> bool:
    # Allowed years: cited items' metadata years UNION years occurring in the cited
    # passages' own text. Allowed pages: cited printed labels and leaf indexes.
    years = {str(h["year"]) for h in cited if h.get("year") is not None}
    for h in cited:
        years.update(_YEAR.findall(h.get("text") or ""))
    pages = {str(h["printed_page"]) for h in cited if h.get("printed_page")} | {str(h["leaf_index"]) for h in cited}
    if any(y not in years for y in _YEAR.findall(text)):
        return True
    return any(p not in pages for p in _PAGE.findall(text))


def _abstain(msg: str, cov: Coverage, unsupported: list[dict]) -> "Answer":
    return Answer(text=msg, sentences=[], verified_citations=[], unsupported=unsupported,
                  abstained=True, coverage=cov, abstention_text=msg)


def compose(question: str, hits: list[dict], llm: LLM, verify: Callable, *,
            min_items: int, min_passages: int) -> Answer:
    cov = coverage_of(hits)
    if is_thin(cov, min_items=min_items, min_passages=min_passages):
        return _abstain(ABSTAIN_THIN.format(n_fts_items=cov.n_fts_items, n_fts_passages=cov.n_fts_passages,
                                            n_undated=cov.n_undated, n_passages=cov.n_passages), cov, [])

    retrieved_ids = [h["passage_id"] for h in hits]
    by_id = {h["passage_id"]: h for h in hits}
    draft = llm.draft(SYSTEM, build_user_prompt(question, hits))

    kept, unsupported, verified = [], [], {}
    for s in draft.sentences:
        cited = list(dict.fromkeys(s.cited_ids))  # dedupe, order-preserving
        row = {"text": s.text, "cited_ids": cited}
        if not cited:
            unsupported.append({**row, "reason": "no citation"})
            continue
        failed = sorted({c.passage_id for c in verify(cited, retrieved_ids) if not c.ok})
        if failed:
            unsupported.append({**row, "reason": f"citation failed verification: {failed}"})
            continue
        cited_hits = [by_id[i] for i in cited]
        if _leaks_facts(s.text, cited_hits):
            unsupported.append({**row, "reason": "mentions a year or page not in the cited passages"})
            continue
        kept.append(row)
        for h in cited_hits:
            verified[h["passage_id"]] = _citation_dict(h)

    if not kept:
        return _abstain(ABSTAIN_UNVERIFIED, cov, unsupported)
    return Answer(text=" ".join(r["text"] for r in kept), sentences=kept,
                  verified_citations=list(verified.values()), unsupported=unsupported,
                  abstained=False, coverage=cov)
