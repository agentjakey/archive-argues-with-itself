"""Reciprocal Rank Fusion and the OCR soft down-weight."""
from __future__ import annotations

from collections import defaultdict

from archive_debugger.ingest.ocr import quality_bucket


def rrf(rank_lists: list[list[str]], k: int = 60) -> dict:
    """rank_lists: ordered passage_id lists, best first. RRF score = sum
    1/(k + rank), rank 1-based."""
    scores = defaultdict(float)
    for ranked in rank_lists:
        for i, pid in enumerate(ranked):
            scores[pid] += 1.0 / (k + i + 1)
    return dict(scores)


def apply_section_weight(scores: dict, section_by_pid: dict, weights: dict) -> dict:
    """Soft multiplier on the fused score by page section class (front/body/back).
    Unknown or NULL class counts as body (1.0). Never excludes."""
    return {
        pid: s * weights.get(section_by_pid.get(pid) or "body", 1.0)
        for pid, s in scores.items()
    }


def apply_downweight(scores: dict, quality_by_pid: dict, weights: dict) -> dict:
    """Soft multiplier on the fused score by passage OCR bucket. Separate from the
    min-ocr hard filter. A passage with unknown quality is treated as high (1.0)."""
    return {
        pid: s * weights[quality_bucket(quality_by_pid.get(pid, 1.0))]
        for pid, s in scores.items()
    }
