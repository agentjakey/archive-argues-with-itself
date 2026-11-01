"""Pure parts of the retrieval ablation (scripts/v2/retrieval_ablation.py): int8 quantization, sign
bits with Hamming search and float rescoring, pool re-ranking, latency summary, and the metered
Workers AI embedding loop with a fake network function. No network, no corpus data."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from archive_debugger.audit.budget import BudgetExceeded, Ledger
from archive_debugger.audit.records import read_jsonl

REPO = Path(__file__).resolve().parent.parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "v2" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ra = load("retrieval_ablation")


def unit_rows(n=300, dim=32, seed=0):
    rng = np.random.default_rng(seed)
    m = rng.standard_normal((n, dim)).astype(np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def test_top_k_desc_orders_best_first_and_breaks_ties_by_index():
    scores = np.array([0.1, 0.9, 0.5, 0.9, 0.2], dtype=np.float32)
    assert ra.top_k_desc(scores, 3).tolist() == [1, 3, 2]
    assert ra.top_k_desc(scores, 10).tolist() == [1, 3, 2, 4, 0]
    assert ra.top_k_desc(scores, 0).tolist() == []


def test_int8_quantization_uses_one_scale_per_dimension_and_stays_close():
    m = unit_rows()
    m[:, 0] *= 0.01                                   # a small dimension gets its own fine scale
    codes, scale = ra.quantize_int8_per_dim(m, block_rows=64)
    assert codes.dtype == np.int8 and codes.shape == m.shape and scale.shape == (m.shape[1],)
    assert np.abs(codes).max() <= 127
    assert scale[0] == pytest.approx(np.abs(m[:, 0]).max() / 127, rel=1e-6)
    assert np.abs(codes.astype(np.float32) * scale - m).max() <= scale.max() / 2 + 1e-7


def test_int8_scores_match_the_dequantized_dot_product_with_and_without_rows():
    m = unit_rows()
    codes, scale = ra.quantize_int8_per_dim(m)
    q = ra.unit(np.arange(1, 33, dtype=np.float32))
    expected = (codes.astype(np.float32) * scale) @ q
    np.testing.assert_allclose(ra.int8_scores(codes, scale, q, block_rows=50), expected, rtol=1e-5, atol=1e-6)
    rows = np.array([5, 7, 299])
    np.testing.assert_allclose(ra.int8_scores(codes, scale, q, rows), expected[rows], rtol=1e-5, atol=1e-6)
    assert np.abs(expected - m @ q).max() < 0.02


def test_int8_index_ranks_like_exact_cosine_on_easy_data():
    m = unit_rows()
    codes, scale = ra.quantize_int8_per_dim(m)
    ids = [f"p{i}" for i in range(m.shape[0])]
    idx = ra.Int8DenseIndex(codes, scale, ids)
    assert idx.search(m[42] * 3.0, None, 1) == ["p42"]
    assert idx.search(m[42], ["p1", "p42", "nope"], 2)[0] == "p42"
    assert idx.search(m[42], ["nope"], 2) == []


def test_pack_signs_and_hamming_match_a_plain_count():
    m = unit_rows(n=50, dim=20)
    packed = ra.pack_signs(m, block_rows=7)
    assert packed.shape == (50, 3) and packed.dtype == np.uint8
    q = m[3]
    qbits = np.packbits(q > 0)
    plain = ((m > 0) != (q > 0)).sum(axis=1)
    assert ra.hamming_distances(packed, qbits).tolist() == plain.tolist()
    assert ra.hamming_distances(packed, qbits, np.array([3, 9])).tolist() == [0, int(plain[9])]


def test_binary_rescore_is_exact_when_every_row_is_rescored():
    m = unit_rows()
    packed = ra.pack_signs(m)
    q = ra.unit(m[10] + 0.3 * m[20])
    exact = ra.top_k_desc(m @ q, 15)
    assert ra.binary_rescore(packed, m, q, 15, rescore_n=m.shape[0]).tolist() == exact.tolist()


def test_binary_rescore_returns_global_rows_for_a_filtered_subset():
    m = unit_rows()
    packed = ra.pack_signs(m)
    rows = np.array([3, 50, 77, 120, 250])
    q = m[77]
    found = ra.binary_rescore(packed, m, q, 2, rescore_n=3, rows=rows)
    assert found[0] == 77 and set(found.tolist()) <= set(rows.tolist())
    assert ra.binary_rescore(packed, m, q, 2, rescore_n=3, rows=np.array([], dtype=np.int64)).tolist() == []


def test_binary_index_finds_the_query_row():
    m = unit_rows()
    idx = ra.BinaryRescoreIndex(ra.pack_signs(m), m, [f"p{i}" for i in range(m.shape[0])], rescore_n=20)
    assert idx.search(m[5], None, 3)[0] == "p5"


def test_rank_pool_orders_by_cosine_and_breaks_ties_by_id():
    vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [2.0, 0.0], "d": [1.0, 1.0]}
    assert ra.rank_pool([1.0, 0.0], ["b", "c", "d", "a"], vectors) == ["a", "c", "d", "b"]


def test_pool_metrics_use_the_eval_metric_functions():
    labels = {"a": 1, "b": 0, "c": 1}
    row = ra.pool_metrics(["a", "b", "c"], labels)
    assert row["recall@5"] == 1.0
    assert row["ndcg@10"] == pytest.approx((1 + 1 / np.log2(4)) / (1 + 1 / np.log2(3)))
    assert ra.pool_metrics(["b"], {"b": 0})["recall@5"] is None


def test_random_order_expectation_matches_every_permutation():
    import itertools
    labels = {"a": 1, "b": 0, "c": 1, "d": 0, "e": 0}
    perms = list(itertools.permutations(labels))
    rows = [ra.pool_metrics(list(p), labels) for p in perms]
    expected = ra.random_order_expectation(5, 2)
    for key in ("recall@5", "recall@10", "ndcg@10"):
        assert expected[key] == pytest.approx(sum(r[key] for r in rows) / len(rows))
    assert ra.random_order_expectation(4, 0)["ndcg@10"] is None


def test_overlap_latency_and_mean():
    assert ra.overlap(["a", "b", "x"], ["a", "b", "c", "d"]) == 0.5
    assert ra.overlap([], []) is None
    s = ra.latency_summary([0.001 * i for i in range(1, 21)])
    assert s == {"n": 20, "median_ms": 10.5, "p95_ms": 19.0}
    assert ra.latency_summary([])["median_ms"] is None
    assert ra.mean4([0.5, None, 0.25]) == 0.375 and ra.mean4([None]) is None


def test_looks_french():
    assert not ra.looks_french("What did federal reports say about the health of aging seniors?")
    assert ra.looks_french("Quels sont les programmes de vaccination dans la province?")
    assert ra.looks_french("Que disent les rapports sur la sant" + chr(0xE9) + " publique?")


def _fake_post(calls, usage=True, cache="MISS"):
    def post(url, headers, body, response_headers=None):
        calls.append((url, headers, body))
        if response_headers is not None:
            response_headers["cf-aig-cache-status"] = cache
        reply = {"data": [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]}
        if usage:
            reply["usage"] = {"prompt_tokens": 10 * len(body["input"])}
        return reply
    return post


def test_workers_ai_embedding_is_metered_batch_by_batch(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    calls = []
    out = ra.embed_workers_ai("@cf/baai/bge-m3", [f"t{i}" for i in range(5)], ledger=ledger,
                              post=_fake_post(calls), account="acct", headers={"authorization": "Bearer x"},
                              run_id="r", run_cap=1.0, batch_size=2)
    assert len(calls) == 3 and len(out["vectors"]) == 5
    assert "/accounts/acct/ai/v1/embeddings" in calls[0][0] and calls[0][2]["model"] == "@cf/baai/bge-m3"
    entries = read_jsonl(tmp_path / "ledger.jsonl")
    assert [e["kind"] for e in entries] == ["reserve", "spend", "release"] * 3
    spends = [e for e in entries if e["kind"] == "spend"]
    assert [e["input_tokens"] for e in spends] == [20, 20, 10]
    assert all(e["output_tokens"] == 0 and e["provider"] == "workers-ai" for e in spends)
    assert ledger.totals("r").reserved == 0
    assert out["estimated_calls"] == 0


def test_missing_usage_records_the_labelled_worst_case(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    out = ra.embed_workers_ai("@cf/qwen/qwen3-embedding-0.6b", ["abc"], ledger=ledger, post=_fake_post([], usage=False),
                              account="a", headers={}, run_id="r", run_cap=1.0)
    spend = [e for e in read_jsonl(tmp_path / "ledger.jsonl") if e["kind"] == "spend"][0]
    assert out["estimated_calls"] == 1 and "worst case" in spend["what"]
    assert spend["input_tokens"] == ra.prices.estimate_input_tokens("abc")


def test_gateway_cache_hit_is_not_billed(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    out = ra.embed_workers_ai("@cf/baai/bge-m3", ["abc"], ledger=ledger, post=_fake_post([], cache="HIT"),
                              account="a", headers={}, run_id="r", run_cap=1.0)
    kinds = [e["kind"] for e in read_jsonl(tmp_path / "ledger.jsonl")]
    assert kinds == ["reserve", "release"] and out["cached_calls"] == 1 and out["usd"] == 0.0


def test_the_cap_stops_before_any_call(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    calls = []
    with pytest.raises(BudgetExceeded):
        ra.embed_workers_ai("@cf/baai/bge-m3", ["x" * 10000], ledger=ledger, post=_fake_post(calls),
                            account="a", headers={}, run_id="r", run_cap=1e-9)
    assert calls == []


def test_embedding_prices_are_input_only():
    assert ra.prices.cost("@cf/baai/bge-m3", 1_000_000, 0) == pytest.approx(0.0118)
    assert ra.prices.cost("@cf/qwen/qwen3-embedding-0.6b", 0, 1_000_000) == 0.0


def test_embedding_cache_round_trips(tmp_path):
    cache = ra.EmbeddingCache(tmp_path / "m.npz")
    cache.vectors[ra.text_key("m", "hello")] = np.array([1.0, 2.0], dtype=np.float32)
    cache.save()
    again = ra.EmbeddingCache(tmp_path / "m.npz")
    np.testing.assert_array_equal(again.vectors[ra.text_key("m", "hello")], [1.0, 2.0])
