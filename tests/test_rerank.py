"""The second ranking stage (retrieve/rerank.py): off unless CIVIC_RERANK_DEPTH is set, reorders only
the pool's head, never changes its members, falls back to the retrieval order on any failure, and keys
the answer cache apart from plain answers (with the same hash the engine Worker computes)."""
from __future__ import annotations

import hashlib

import pytest

from archive_debugger.retrieve import rerank


def rows(n):
    return [{"passage_id": f"p{i}", "text": f"text {i}"} for i in range(n)]


def test_off_by_default_and_on_with_a_depth():
    assert rerank.settings({}) is None
    assert rerank.settings({"CIVIC_RERANK_DEPTH": "0"}) is None
    assert rerank.settings({"CIVIC_RERANK_DEPTH": "20"}) == {"model": "@cf/baai/bge-reranker-base", "depth": 20}
    assert rerank.settings({"CIVIC_RERANK_DEPTH": "x"}) is None


def test_routes_through_the_proxy_in_the_container_and_rest_elsewhere():
    url, headers = rerank.transport({"CIVIC_AI_PROXY_URL": "http://ai.internal", "CIVIC_CACHE_TOKEN": "t"})
    assert url == "http://ai.internal/v1/rerank" and headers["authorization"] == "Bearer t"
    url, _ = rerank.transport({"CF_ACCOUNT_ID": "acc", "CF_AI_TOKEN": "k"})
    assert url == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/baai/bge-reranker-base"
    assert rerank.transport({}) is None


def test_reorders_only_the_head_and_keeps_every_passage():
    env = {"CF_ACCOUNT_ID": "acc", "CF_AI_TOKEN": "k"}
    sent = {}

    def post(url, headers, body):
        sent.update(body)
        # best first: 2, 0, 1
        return {"result": {"response": [{"id": 0, "score": 0.5}, {"id": 2, "score": 0.9}, {"id": 1, "score": 0.1}]}}

    out, info = rerank.rerank("q", rows(5), 3, env=env, post=post)
    assert [r["passage_id"] for r in out] == ["p2", "p0", "p1", "p3", "p4"]
    assert info["reranked"] is True and len(sent["contexts"]) == 3


@pytest.mark.parametrize("reply", [{"result": {"response": [{"id": 0, "score": 1}]}}, {}, None])
def test_a_bad_reply_or_a_failure_keeps_the_retrieval_order(reply):
    env = {"CF_ACCOUNT_ID": "acc", "CF_AI_TOKEN": "k"}

    def post(url, headers, body):
        if reply is None:
            raise TimeoutError("slow")
        return reply

    out, info = rerank.rerank("q", rows(4), 4, env=env, post=post)
    assert [r["passage_id"] for r in out] == ["p0", "p1", "p2", "p3"]
    assert info["reranked"] is False and info["error"]


def test_the_cache_key_changes_with_the_reranker_and_matches_the_worker():
    from archive_debugger.api.app import cache_context
    g = {"answer_version": "v2", "provider": "workers_ai", "model": "m", "max_tokens": 10, "top_k": 12,
         "temperature": None, "effort": None, "extra_body": None, "rank": None}
    data = {"db": "a" * 64, "index": "b" * 64}
    plain = cache_context("pilot", data, {}, g, "workers_ai", "m")
    reranked = cache_context("pilot", data, {}, dict(g, rerank={"model": rerank.MODEL, "depth": 20}),
                             "workers_ai", "m")
    assert reranked != plain
    assert reranked == hashlib.sha256(f"{plain}|rerank:{rerank.MODEL}:20".encode()).hexdigest()
