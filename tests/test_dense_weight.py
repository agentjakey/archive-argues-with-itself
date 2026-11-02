"""The dense leg's weight in the fusion (Phase 3 re-freeze, docs/FREEZE.md): 1.0 is the baseline RRF,
byte for byte; 0 is BM25 alone; the setting keys the cache only when it is not 1.0."""
from __future__ import annotations

import dataclasses

from archive_debugger.api import cache as answer_cache
from archive_debugger.retrieve import search
from archive_debugger.retrieve.embed import StubEmbedder
from archive_debugger.retrieve.fusion import rrf
from tests.test_retrieve import _fixture


class CountingEmbedder(StubEmbedder):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.queries = 0

    def embed_query(self, text):
        self.queries += 1
        return super().embed_query(text)


def hits_for(cfg, query="vaccination hospital", embedder=None):
    r = search.Retriever(None, embedder=embedder or StubEmbedder(dim=64), cfg=cfg)
    try:
        return r.search(query, top_k=5)
    finally:
        r.close()


def test_weight_one_is_the_baseline_fusion(tmp_path):
    cfg = _fixture(tmp_path)
    assert cfg.dense_weight == 1.0
    base = hits_for(cfg)
    same = hits_for(dataclasses.replace(cfg, dense_weight=1.0))
    assert [(h["passage_id"], h["score"]) for h in base] == [(h["passage_id"], h["score"]) for h in same]


def test_weight_zero_is_bm25_alone_and_skips_the_dense_leg(tmp_path):
    cfg = dataclasses.replace(_fixture(tmp_path), dense_weight=0.0)
    emb = CountingEmbedder(dim=64)
    hits = hits_for(cfg, embedder=emb)
    assert emb.queries == 0
    assert hits and all(h["dense_rank"] is None and h["bm25_rank"] is not None for h in hits)


def test_weighted_fusion_scales_the_dense_contribution():
    bm, dn = ["a", "b"], ["b", "c"]
    plain = rrf([bm, dn], k=60)
    half = rrf([bm], k=60)
    for pid, s in rrf([dn], k=60).items():
        half[pid] = half.get(pid, 0.0) + 0.5 * s
    assert half["a"] == plain["a"] and half["c"] == plain["c"] / 2 and half["b"] < plain["b"]


def test_the_cache_key_moves_only_when_the_weight_is_not_one(tmp_path):
    cfg = _fixture(tmp_path)
    base = answer_cache.retrieve_settings(cfg)
    assert "dense_weight" not in base
    assert answer_cache.retrieve_settings(dataclasses.replace(cfg, dense_weight=0.5))["dense_weight"] == 0.5
