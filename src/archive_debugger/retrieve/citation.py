"""Page-level citations (Phase 8) and the deterministic 3-check verifier (N2).

Single source of truth for the fixed IA deep-link format and the citation object.
Page-level only: passage -> (item, leaf, printed_page?, deep_link). No coordinate
fields are ever stored or returned (N3); items.has_word_coords stays a capability
flag and is untouched here.

The verifier is structural and deterministic: it never uses lexical/embedding
overlap (a triage flag only, never citation correctness -- N2), never calls an LLM,
and is not wired to generation. The >=90% citation-support metric comes from the
manual claim-level audit, not from this function."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Optional


def deep_link(item_id: str, leaf_index: int) -> str:
    """The fixed IA page deep-link. One definition, used everywhere."""
    return f"https://archive.org/details/{item_id}/page/n{leaf_index}"


@dataclass(frozen=True)
class Citation:
    passage_id: str
    item_id: str
    leaf_index: int
    printed_page: Optional[str]   # nullable; printed label only when the item has a page map
    deep_link: str
    # N3: no bbox/coordinate fields, ever.

    def to_dict(self) -> dict:
        return asdict(self)


def citation_for(conn: sqlite3.Connection, passage_id: str) -> Optional[Citation]:
    """Page-level citation for a passage, or None if it cannot resolve to a real
    recorded page/item. LEFT JOIN so a missing page/item yields None, not a
    spurious row. deep_link always keys on leaf_index (page level), never on the
    printed label."""
    r = conn.execute(
        "SELECT i.item_id AS item_id, g.leaf_index AS leaf_index, g.printed_page AS printed_page "
        "FROM passages p LEFT JOIN pages g ON g.page_id = p.page_id "
        "LEFT JOIN items i ON i.item_id = p.item_id WHERE p.passage_id = ?",
        (passage_id,),
    ).fetchone()
    if r is None or r["item_id"] is None or r["leaf_index"] is None:
        return None
    return Citation(passage_id=passage_id, item_id=r["item_id"], leaf_index=r["leaf_index"],
                    printed_page=r["printed_page"], deep_link=deep_link(r["item_id"], r["leaf_index"]))


@dataclass(frozen=True)
class CitationCheck:
    passage_id: str
    exists: bool          # (1) the cited passage_id exists
    in_evidence: bool     # (2) it was in the retrieved evidence for the query
    resolves: bool        # (3) it resolves to a real recorded source page (valid deep link)
    deep_link: Optional[str]

    @property
    def ok(self) -> bool:
        return self.exists and self.in_evidence and self.resolves

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def verify_citation(conn: sqlite3.Connection, passage_id: str, retrieved_ids) -> CitationCheck:
    """Three deterministic checks (N2). `retrieved_ids` is the evidence set returned
    for THAT query (whatever the caller retrieved) -- this function does not run
    retrieval or generation, and uses no overlap heuristics or LLM."""
    exists = conn.execute("SELECT 1 FROM passages WHERE passage_id = ?", (passage_id,)).fetchone() is not None
    in_evidence = passage_id in set(retrieved_ids)
    cit = citation_for(conn, passage_id) if exists else None
    return CitationCheck(passage_id=passage_id, exists=exists, in_evidence=in_evidence,
                         resolves=cit is not None, deep_link=cit.deep_link if cit else None)


def verify_citations(conn: sqlite3.Connection, cited_ids, retrieved_ids) -> list[CitationCheck]:
    evidence = set(retrieved_ids)
    return [verify_citation(conn, pid, evidence) for pid in cited_ids]
