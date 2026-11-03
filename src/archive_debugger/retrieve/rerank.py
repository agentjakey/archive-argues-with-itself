"""A second ranking stage after retrieval, behind a flag: the Workers AI cross-encoder
(@cf/baai/bge-reranker-base) reorders the first `depth` passages of the retrieved pool; the rest keep
their order, and no passage joins or leaves the pool. Off unless CIVIC_RERANK_DEPTH is a positive
number. The frozen retrieval (retrieve/search.py) is not touched: this runs on its output.

Two ways to reach the model, chosen from the environment:
  the engine container   CIVIC_AI_PROXY_URL + CIVIC_CACHE_TOKEN (the engine Worker's AIProxy, which
                         calls its AI binding; no Workers AI token is in the container)
  a laptop or CI runner  CF_ACCOUNT_ID + CF_AI_TOKEN (the Workers AI REST API)

A failed call never fails an answer: the pool keeps its retrieval order and the reply says so in its
generation metadata. There is one network function, _post, which tests replace.

Measured on the ablation sub-corpora (2026-11-02, BM25's top 30): source page in the first ten +6.9
points over BM25 alone [+2.5, +11.3], median 1.0 s, about $0.00005 a question."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Callable, Optional

MODEL = "@cf/baai/bge-reranker-base"
DEPTH_ENV = "CIVIC_RERANK_DEPTH"
MAX_CHARS = 2000            # the passage text sent per context, as in the ablation
TIMEOUT_S = 6.0
REST_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

# Set by a metered run (scripts/v2/run_benchmark.py) to record each call's tokens in the audit ledger.
METER: Optional[Callable[[int, int], None]] = None   # (tokens, passages) -> None


def depth_from_env(env: Optional[dict] = None) -> int:
    env = os.environ if env is None else env
    try:
        return max(0, int(env.get(DEPTH_ENV) or 0))
    except ValueError:
        return 0


def settings(env: Optional[dict] = None) -> Optional[dict]:
    """{"model", "depth"} when the flag is on, else None. Joins the answer cache key (api/app.py), so a
    reranked answer is never served for a plain one or the other way round."""
    depth = depth_from_env(env)
    return {"model": MODEL, "depth": depth} if depth else None


def transport(env: Optional[dict] = None) -> Optional[tuple]:
    """(url, headers) for the reranker, or None when this environment has no way to reach it."""
    env = os.environ if env is None else env
    proxy = env.get("CIVIC_AI_PROXY_URL")
    if proxy and env.get("CIVIC_CACHE_TOKEN"):
        return (proxy.rstrip("/") + "/v1/rerank", {"authorization": f"Bearer {env['CIVIC_CACHE_TOKEN']}"})
    if env.get("CF_ACCOUNT_ID") and env.get("CF_AI_TOKEN"):
        return (REST_URL.format(account=env["CF_ACCOUNT_ID"], model=MODEL),
                {"authorization": f"Bearer {env['CF_AI_TOKEN']}"})
    return None


def _post(url: str, headers: dict, body: dict, timeout: float = TIMEOUT_S) -> dict:
    """The one network call: POST JSON, return JSON. Raises on any failure (the caller falls back)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={**headers, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310 - fixed https or proxy host
        return json.loads(resp.read().decode("utf-8"))


def order_from_reply(reply: dict, n: int) -> list:
    """The passage order, best first, from a Workers AI rerank reply (REST wraps it in "result").
    Raises when the reply does not rank every passage exactly once."""
    result = reply.get("result", reply) if isinstance(reply, dict) else {}
    ranked = sorted(result.get("response") or [], key=lambda r: -float(r.get("score") or 0.0))
    order = [int(r["id"]) for r in ranked if 0 <= int(r.get("id", -1)) < n]
    if sorted(order) != list(range(n)):
        raise ValueError("the reranker did not rank every passage once")
    return order


def usage_tokens(reply: dict) -> int:
    result = reply.get("result", reply) if isinstance(reply, dict) else {}
    usage = result.get("usage") or {}
    return int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)


def rerank(question: str, rows: list, depth: int, *, env: Optional[dict] = None,
           post: Optional[Callable] = None) -> tuple:
    """(rows, info): the first `depth` rows reordered by the reranker, the rest after them unchanged.
    info = {"model", "depth", "reranked": bool, "seconds", "error"?}. Rows are dicts with "text"."""
    info: dict = {"model": MODEL, "depth": depth, "reranked": False}
    head = list(rows[:depth])
    if depth <= 0 or len(head) < 2:
        return list(rows), info
    where = transport(env)
    if where is None:
        info["error"] = "no route to the reranker"
        return list(rows), info
    url, headers = where
    contexts = [{"text": (r.get("text") or "")[:MAX_CHARS] or " "} for r in head]
    t0 = time.perf_counter()
    try:
        reply = (post or _post)(url, headers, {"query": question, "contexts": contexts, "top_k": len(contexts)})
        order = order_from_reply(reply, len(head))
    except Exception as exc:  # noqa: BLE001 - any failure: keep the retrieval order
        info.update(seconds=round(time.perf_counter() - t0, 3), error=type(exc).__name__)
        return list(rows), info
    info.update(reranked=True, seconds=round(time.perf_counter() - t0, 3))
    if METER is not None:
        METER(usage_tokens(reply), len(head))
    return [head[i] for i in order] + list(rows[depth:]), info
