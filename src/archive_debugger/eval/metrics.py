"""Retrieval metrics, computed ONLY from human labels. Embedding/lexical overlap
is never used as ground truth (N2)."""
from __future__ import annotations

import math


def recall_at_k(ranked: list[str], gold: set, k: int):
    """Fraction of human-relevant passages retrieved in the top k. None when there
    is no positive gold (undefined, not zero)."""
    if not gold:
        return None
    return len(set(ranked[:k]) & set(gold)) / len(gold)


def dcg(rels: list[float]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))


def ndcg_at_k(ranked: list[str], gold_rel: dict, k: int):
    """gold_rel: {passage_id: relevance >= 0}. None when there is no positive gold."""
    ideal = sorted((v for v in gold_rel.values() if v > 0), reverse=True)[:k]
    idcg = dcg(ideal)
    if idcg == 0:
        return None
    rels = [max(0, gold_rel.get(pid, 0)) for pid in ranked[:k]]
    return dcg(rels) / idcg


def unjudged_at_k(ranked: list[str], judged: set, k: int):
    """Share of the top k that carries NO human label for this question. Gold was
    pooled from one retriever's top-N, so a changed ranking surfaces unjudged
    passages; this is the honesty column beside recall. None when nothing was
    retrieved. Denominator is the retrieved prefix (shorter than k when the ranking
    is short, e.g. under a per-item cap with narrow filters)."""
    top = ranked[:k]
    if not top:
        return None
    return sum(1 for pid in top if pid not in judged) / len(top)


def relevant_in_topk(ranked: list[str], gold_rel: dict, k: int) -> int:
    return sum(1 for pid in ranked[:k] if gold_rel.get(pid, 0) > 0)


def system_has_evidence(ranked, gold_rel, k, min_relevant) -> bool:
    """True when at least min_relevant human-relevant passages appear in the top k;
    below that the system is signaling thin evidence (abstaining)."""
    return relevant_in_topk(ranked, gold_rel, k) >= min_relevant


def abstention_correct(ranked, gold_rel, answerable, k, min_relevant) -> bool:
    """Correct when the system's evidence signal matches the human verdict:
    answerable -> has evidence; should-abstain -> thin. Human labels only.

    Defined for Phase 9; NOT aggregated in the Phase 7 report (for should-abstain
    questions gold is empty, so this is True by construction and meaningless as a
    rate)."""
    return system_has_evidence(ranked, gold_rel, k, min_relevant) == bool(answerable)
