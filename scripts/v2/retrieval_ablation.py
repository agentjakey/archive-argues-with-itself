"""Phase 2 Part A retrieval ablation over the v1 retrieval gold. No answer-model calls.

Arms scored corpus-wide with the production Retriever (config as-is for the scope; only the dense
candidate leg is swapped, everything else in Retriever.search is unchanged: BM25, RRF, OCR
down-weight, section demotion, per-item cap, filters):
  bm25_only              the dense leg returns nothing, so the ranking is the FTS side alone
  hybrid_exact           float32 dense via the numpy backend (retrieve.dense.DenseIndex) + BM25
  hybrid_int8            int8 dense codes with one symmetric scale per dimension, scored directly
  hybrid_binary_rescore  sign bits, Hamming top-N (N = --rescore), then exact float32 cosine on those N

Pool arms (no corpus scan): every judged passage of a question is re-ranked against the question
by one embedder: MiniLM (the stored index vectors, the like-for-like baseline),
snowflake/snowflake-arctic-embed-m (fastembed, local), and the Workers AI embedders @cf/baai/bge-m3
and @cf/qwen/qwen3-embedding-0.6b (paid, metered through the audit ledger under run
"ablation-embed-1" with a $1.00 run cap; every call reserves its worst case first).

Metrics come from archive_debugger.eval.report.evaluate and eval.metrics, over the gold stored in
each scope's corpus database (eval_questions, eval_question_gold, eval_labels), read-only.

Run (one scope per process keeps memory down; the report is assembled from every scope checkpoint):
    .venv/Scripts/python.exe scripts/v2/retrieval_ablation.py --scope pilot
    .venv/Scripts/python.exe scripts/v2/retrieval_ablation.py --scope microlog
    .venv/Scripts/python.exe scripts/v2/retrieval_ablation.py --report-only
Flags: --skip-paid (no Workers AI calls), --skip-pool, --pool-only (recompute the pool arms into an
existing checkpoint, from cached embeddings where present), --rescore N (binary candidates, default 2000).

Writes:
    reports/v2/raw/ablation/<scope>.json          one checkpoint per scope
    reports/v2/raw/ablation/embeddings/*.npz      cached pool embeddings, so a rerun never pays twice
    reports/v2/baseline/retrieval_ablation.json   raw results, both scopes, per question
    reports/v2/baseline/retrieval_ablation.md     summary tables
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import sys
import time
import tomllib
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger import scopes  # noqa: E402
from archive_debugger.audit import judges, net, prices  # noqa: E402
from archive_debugger.audit.budget import BudgetExceeded, Ledger  # noqa: E402
from archive_debugger.audit.records import iter_jsonl  # noqa: E402
from archive_debugger.eval import metrics, report, rundb, store  # noqa: E402
from archive_debugger.eval.label import filters_from  # noqa: E402

RAW_DIR = REPO / "reports" / "v2" / "raw" / "ablation"
EMBED_CACHE_DIR = RAW_DIR / "embeddings"
OUT_JSON = REPO / "reports" / "v2" / "baseline" / "retrieval_ablation.json"
OUT_MD = REPO / "reports" / "v2" / "baseline" / "retrieval_ablation.md"
LEDGER_PATH = REPO / "reports" / "v2" / "audit" / "ledger.jsonl"
AUDIT_CONFIG = REPO / "config" / "audit.toml"

RUN_ID = "ablation-embed-1"
RUN_CAP_USD = 1.00
BATCH_TEXTS = 50
RECALL_KS = (5, 10, 20)
NDCG_K = 10
TOP_N = 30
DEFAULT_RESCORE = 2000
BLOCK_ROWS = 65536
WORKERS_AI_EMBED_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/embeddings"

ARMS = ("bm25_only", "hybrid_exact", "hybrid_int8", "hybrid_binary_rescore")

NEWLINE = chr(10)
# Query prefixes from each model's own card. MiniLM and bge-m3 take the question as it is.
ARCTIC_MODEL = "snowflake/snowflake-arctic-embed-m"
ARCTIC_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
QWEN_QUERY_PREFIX = ("Instruct: Given a web search query, retrieve relevant passages that answer the query"
                     + NEWLINE + "Query:")
POOL_MODELS = (
    # name, kind, model id, query prefix, licence, max input tokens
    ("minilm", "stored", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "", "Apache-2.0", 128),
    ("arctic-embed-m", "fastembed", ARCTIC_MODEL, ARCTIC_QUERY_PREFIX, "Apache-2.0", 512),
    ("bge-m3", "workers-ai", "@cf/baai/bge-m3", "", "MIT", 60000),
    ("qwen3-embedding-0.6b", "workers-ai", "@cf/qwen/qwen3-embedding-0.6b", QWEN_QUERY_PREFIX, "Apache-2.0", 8192),
)


def log(msg: str) -> None:
    print(msg, flush=True)


# --- pure functions (unit tested in tests/test_retrieval_ablation.py) ------------------------------

def unit(vec) -> np.ndarray:
    """A float32 copy of vec scaled to length 1 (a zero vector stays zero)."""
    v = np.asarray(vec, dtype=np.float32).copy()
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


def top_k_desc(scores: np.ndarray, k: int) -> np.ndarray:
    """Indices of the k largest scores, best first; ties broken by lower index."""
    n = scores.shape[0]
    if k <= 0 or n == 0:
        return np.empty(0, dtype=np.int64)
    if k < n:
        part = np.argpartition(-scores, k - 1)[:k]
    else:
        part = np.arange(n)
    order = np.lexsort((part, -scores[part]))
    return part[order]


def quantize_int8_per_dim(matrix: np.ndarray, block_rows: int = BLOCK_ROWS) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric int8 codes with one scale per dimension: scale_d = max |x_d| / 127 over all rows,
    code = round(x / scale) clipped to [-127, 127]. Done in blocks of rows so no full float
    temporary is made."""
    n, dim = matrix.shape
    max_abs = np.zeros(dim, dtype=np.float32)
    for start in range(0, n, block_rows):
        np.maximum(max_abs, np.abs(matrix[start:start + block_rows]).max(axis=0), out=max_abs)
    max_abs[max_abs == 0] = 1.0
    scale = (max_abs / 127.0).astype(np.float32)
    codes = np.empty((n, dim), dtype=np.int8)
    for start in range(0, n, block_rows):
        block = np.rint(matrix[start:start + block_rows] / scale)
        codes[start:start + block_rows] = np.clip(block, -127, 127).astype(np.int8)
    return codes, scale


def int8_scores(codes: np.ndarray, scale: np.ndarray, query_unit: np.ndarray, rows: Optional[np.ndarray] = None,
                block_rows: int = BLOCK_ROWS) -> np.ndarray:
    """Dot products of the dequantized rows with a unit query: codes @ (scale * q), block by block."""
    weights = (np.asarray(query_unit, dtype=np.float32) * scale).astype(np.float32)
    source = codes if rows is None else codes[rows]
    out = np.empty(source.shape[0], dtype=np.float32)
    for start in range(0, source.shape[0], block_rows):
        out[start:start + block_rows] = source[start:start + block_rows].astype(np.float32) @ weights
    return out


def pack_signs(matrix: np.ndarray, block_rows: int = BLOCK_ROWS) -> np.ndarray:
    """One bit per dimension, set when the value is above zero, packed 8 to a byte (numpy packbits
    order). An (n, dim) float matrix becomes (n, ceil(dim / 8)) uint8."""
    n, dim = matrix.shape
    packed = np.empty((n, (dim + 7) // 8), dtype=np.uint8)
    for start in range(0, n, block_rows):
        packed[start:start + block_rows] = np.packbits(matrix[start:start + block_rows] > 0, axis=1)
    return packed


def hamming_distances(packed: np.ndarray, query_bits: np.ndarray, rows: Optional[np.ndarray] = None) -> np.ndarray:
    """Hamming distance from every packed row (or the listed rows) to the packed query."""
    source = packed if rows is None else packed[rows]
    return np.bitwise_count(np.bitwise_xor(source, query_bits)).sum(axis=1, dtype=np.int32)


def binary_rescore(packed: np.ndarray, matrix: np.ndarray, query_unit: np.ndarray, k: int, rescore_n: int,
                   rows: Optional[np.ndarray] = None) -> np.ndarray:
    """Global row numbers of the top k: the rescore_n rows nearest by Hamming distance (over all rows,
    or only the listed rows), re-ranked by exact float cosine against the unit query."""
    query_bits = np.packbits(np.asarray(query_unit) > 0)
    dist = hamming_distances(packed, query_bits, rows)
    n_source = dist.shape[0]
    if n_source == 0:
        return np.empty(0, dtype=np.int64)
    m = min(rescore_n, n_source)
    if m < n_source:
        cand = np.argpartition(dist, m - 1)[:m]
    else:
        cand = np.arange(n_source)
    global_rows = cand if rows is None else np.asarray(rows)[cand]
    sims = matrix[global_rows] @ np.asarray(query_unit, dtype=np.float32)
    return global_rows[top_k_desc(sims, min(k, m))]


def rank_pool(query_vec, pool_ids: list, vectors: dict) -> list:
    """The pool's passage ids by cosine to the query, best first; ties by passage id."""
    q = unit(query_vec)
    scored = [(-float(unit(vectors[pid]) @ q), pid) for pid in pool_ids]
    return [pid for _, pid in sorted(scored)]


def overlap(found: list, reference: list) -> Optional[float]:
    """Share of the reference list that the found list also holds (set overlap at the same k)."""
    if not reference:
        return None
    return len(set(found) & set(reference)) / len(reference)


def latency_summary(seconds: list) -> dict:
    """Median and p95 in milliseconds. p95 is nearest-rank: the ceil(0.95 n)-th smallest value."""
    if not seconds:
        return {"n": 0, "median_ms": None, "p95_ms": None}
    ordered = sorted(seconds)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    return {"n": len(ordered), "median_ms": round(statistics.median(ordered) * 1000, 2), "p95_ms": round(p95 * 1000, 2)}


_FRENCH_WORDS = {"le", "la", "les", "des", "du", "de", "et", "est", "une", "un", "que", "qui", "quels", "quelles",
                 "quel", "quelle", "dans", "pour", "sur", "au", "aux", "par", "comment", "rapport", "sante", "ont"}
_WORD = re.compile(r"[a-z]+")
# a-grave, a-circumflex, c-cedilla, e-grave, e-acute, e-circumflex, e-diaeresis, i-circumflex,
# i-diaeresis, o-circumflex, u-grave, u-circumflex (built from code points to keep this file ASCII)
_FRENCH_ACCENTS = "".join(chr(c) for c in (0xE0, 0xE2, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEE, 0xEF, 0xF4, 0xF9, 0xFB))


def looks_french(text: str) -> bool:
    """A plain heuristic for the subset split: French accents, or at least three French function words
    and more French than English ones. Not a language detector; the question list is short enough
    to read."""
    lowered = text.lower()
    if any(ch in lowered for ch in _FRENCH_ACCENTS):
        return True
    words = _WORD.findall(lowered)
    french = sum(1 for w in words if w in _FRENCH_WORDS)
    english = sum(1 for w in words if w in {"the", "and", "what", "how", "did", "of", "about", "report", "reports"})
    return french >= 3 and french > english


def mean4(values: list) -> Optional[float]:
    defined = [v for v in values if v is not None]
    return round(sum(defined) / len(defined), 4) if defined else None


def pool_metrics(ranked: list, labels: dict) -> dict:
    """recall@5/10/20 and nDCG@10 of a ranking against one question's labels (eval.metrics)."""
    gold_pos = {pid for pid, rel in labels.items() if rel > 0}
    row = {f"recall@{k}": metrics.recall_at_k(ranked, gold_pos, k) for k in RECALL_KS}
    row[f"ndcg@{NDCG_K}"] = metrics.ndcg_at_k(ranked, labels, NDCG_K)
    return row


def text_key(model: str, text: str) -> str:
    return hashlib.sha256((model + NEWLINE + text).encode("utf-8")).hexdigest()


# --- dense legs -------------------------------------------------------------------------------------

class _RowIndex:
    def __init__(self, ids: list):
        self._ids = ids
        self._row = {pid: i for i, pid in enumerate(ids)}

    def _rows(self, allowed_ids: Optional[list]) -> Optional[np.ndarray]:
        if allowed_ids is None:
            return None
        return np.fromiter((self._row[p] for p in allowed_ids if p in self._row), dtype=np.int64)


class Int8DenseIndex(_RowIndex):
    """int8 codes with a per-dimension scale; scores the codes directly (no float rescoring)."""

    def __init__(self, codes: np.ndarray, scale: np.ndarray, ids: list):
        super().__init__(ids)
        self.codes, self.scale = codes, scale

    def search(self, qvec, allowed_ids: Optional[list], k: int) -> list:
        q = unit(qvec)
        rows = self._rows(allowed_ids)
        if rows is not None and rows.size == 0:
            return []
        order = top_k_desc(int8_scores(self.codes, self.scale, q, rows), k)
        found = order if rows is None else rows[order]
        return [self._ids[i] for i in found]


class BinaryRescoreIndex(_RowIndex):
    """Sign bits searched by Hamming distance, then float32 cosine on the rescore_n nearest."""

    def __init__(self, packed: np.ndarray, matrix: np.ndarray, ids: list, rescore_n: int):
        super().__init__(ids)
        self.packed, self.matrix, self.rescore_n = packed, matrix, rescore_n

    def search(self, qvec, allowed_ids: Optional[list], k: int) -> list:
        rows = self._rows(allowed_ids)
        if rows is not None and rows.size == 0:
            return []
        found = binary_rescore(self.packed, self.matrix, unit(qvec), k, self.rescore_n, rows)
        return [self._ids[i] for i in found]


class TimedDense:
    """Wraps a dense index: times each search and, given a reference index, records how much of the
    reference's candidate list this index also returned."""

    def __init__(self, inner, reference=None):
        self.inner, self.reference = inner, reference
        self.seconds: list = []
        self.overlaps: list = []

    def search(self, qvec, allowed_ids, k):
        t0 = time.perf_counter()
        out = self.inner.search(qvec, allowed_ids, k)
        self.seconds.append(time.perf_counter() - t0)
        if self.reference is not None:
            self.overlaps.append(overlap(out, self.reference.search(qvec, allowed_ids, k)))
        return out

    def reset(self) -> None:
        self.seconds, self.overlaps = [], []


class TimedSearch:
    """Wraps a Retriever so eval.report.evaluate can call it while each search is timed."""

    def __init__(self, retriever):
        self.retriever = retriever
        self.seconds: list = []

    def search(self, query, filters=None, top_k=20):
        t0 = time.perf_counter()
        out = self.retriever.search(query, filters=filters, top_k=top_k)
        self.seconds.append(time.perf_counter() - t0)
        return out


class CachedQueryEmbedder:
    """The production embedder with each question embedded once, so search timings exclude it."""

    def __init__(self, inner):
        self.inner = inner
        self.dim = inner.dim
        self.vectors: dict = {}
        self.seconds: dict = {}

    def embed_query(self, text: str):
        if text not in self.vectors:
            t0 = time.perf_counter()
            self.vectors[text] = self.inner.embed_query(text)
            self.seconds[text] = time.perf_counter() - t0
        return self.vectors[text]

    def embed_passages(self, texts):
        return self.inner.embed_passages(texts)


def traced(build: Callable):
    """Run build() under tracemalloc: (result, bytes still held afterwards, peak bytes during)."""
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    result = build()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, current - base, peak - base


# --- pool embeddings ----------------------------------------------------------------------------------

class EmbeddingCache:
    """Vectors keyed by sha256(model + text), kept in one .npz per model (no pickle)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.vectors: dict = {}
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as data:
                for key, vec in zip(data["keys"].tolist(), data["vectors"]):
                    self.vectors[key.decode("ascii")] = vec

    def save(self) -> None:
        if not self.vectors:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = np.array([k.encode("ascii") for k in self.vectors], dtype="S64")
        vectors = np.stack([np.asarray(v, dtype=np.float32) for v in self.vectors.values()])
        tmp = self.path.with_suffix(".tmp.npz")
        np.savez(tmp, keys=keys, vectors=vectors)
        os.replace(tmp, self.path)


def embed_workers_ai(model: str, texts: list, *, ledger: Ledger, post: Callable, account: str, headers: dict,
                     run_id: str = RUN_ID, run_cap: float = RUN_CAP_USD, batch_size: int = BATCH_TEXTS,
                     on_batch: Optional[Callable[[list, list], None]] = None) -> dict:
    """Embed texts through the Workers AI OpenAI-compatible endpoint, batch by batch. Before each call
    its worst case (prices.estimate_input_tokens per text, at list price) is reserved under the run
    and phase caps; BudgetExceeded stops the run before the call. After the call the reported token
    count is recorded (or the worst-case estimate, labelled, when usage is missing; nothing when the
    gateway served the reply from its cache), and the reservation is released.
    Returns {"vectors": [...], "calls": n, "estimated_calls": n, "cached_calls": n, "usd": spent}."""
    url = WORKERS_AI_EMBED_URL.format(account=account)
    out: list = []
    stats = {"calls": 0, "estimated_calls": 0, "cached_calls": 0, "usd": 0.0}
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        estimate = sum(prices.estimate_input_tokens(t) for t in batch)
        worst = prices.cost(model, estimate, 0)
        reservation = f"{run_id}:{model}:{start}:{time.time_ns()}"
        ledger.reserve(run_id, run_cap, "workers-ai", model, reservation, worst)
        try:
            reply_headers: dict = {}
            reply = post(url, headers, {"model": model, "input": batch}, response_headers=reply_headers)
            stats["calls"] += 1
            usage = reply.get("usage") or {}
            tokens = int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
            estimated = tokens <= 0
            if estimated:
                tokens = estimate
                stats["estimated_calls"] += 1
            if str(reply_headers.get("cf-aig-cache-status", "")).upper() == "HIT":
                stats["cached_calls"] += 1
            else:
                what = f"ablation pool embeddings {len(batch)} texts" + (" (usage not reported: worst case)" if estimated else "")
                stats["usd"] += ledger.spend(run_id, "workers-ai", model, tokens, 0, what=what)
        finally:
            ledger.release(run_id, reservation)
        data = sorted(reply.get("data") or [], key=lambda d: d.get("index", 0))
        if len(data) != len(batch):
            raise ValueError(f"{model}: asked for {len(batch)} embeddings, got {len(data)}")
        vectors = [np.asarray(d["embedding"], dtype=np.float32) for d in data]
        out.extend(vectors)
        if on_batch is not None:
            on_batch(batch, vectors)
    stats["vectors"] = out
    return stats


def _gateway_name() -> Optional[str]:
    with AUDIT_CONFIG.open("rb") as fh:
        return (tomllib.load(fh).get("gateway") or {}).get("workers_ai") or None


def embed_with_cache(name: str, kind: str, model: str, texts: list, *, ledger: Optional[Ledger],
                     skip_paid: bool) -> tuple[dict, dict]:
    """{text: vector} for every text (from the cache where present), plus call stats."""
    cache = EmbeddingCache(EMBED_CACHE_DIR / f"{name}.npz")
    missing = [t for t in dict.fromkeys(texts) if text_key(model, t) not in cache.vectors]
    stats: dict = {"cached_texts": len(set(texts)) - len(missing), "embedded_texts": len(missing)}
    if missing and kind == "fastembed":
        from fastembed import TextEmbedding
        t0 = time.perf_counter()
        engine = TextEmbedding(model_name=model)
        for start in range(0, len(missing), 64):
            batch = missing[start:start + 64]
            for text, vec in zip(batch, engine.embed(batch)):
                cache.vectors[text_key(model, text)] = np.asarray(vec, dtype=np.float32)
        stats["seconds"] = round(time.perf_counter() - t0, 1)
        cache.save()
    elif missing and kind == "workers-ai":
        if skip_paid:
            raise RuntimeError("skip-paid")
        account, token = judges.workers_ai_credentials()
        headers = judges.workers_ai_headers(token, _gateway_name())

        def keep(batch, vectors):
            for text, vec in zip(batch, vectors):
                cache.vectors[text_key(model, text)] = vec
            cache.save()

        result = embed_workers_ai(model, missing, ledger=ledger, post=net.post_json, account=account,
                                  headers=headers, on_batch=keep)
        stats.update({k: v for k, v in result.items() if k != "vectors"})
    return {t: cache.vectors[text_key(model, t)] for t in texts}, stats


# --- the run ------------------------------------------------------------------------------------------

def load_gold(conn) -> list:
    """Labeled questions with their labels, exactly as eval.report.evaluate reads them."""
    out = []
    for q in store.list_questions(conn):
        verdict = store.gold_verdict(conn, q["qid"])
        if verdict is None:
            continue
        out.append({**q, "answerable": verdict["answerable"], "labels": store.get_labels(conn, q["qid"])})
    return out


def passage_texts(conn, ids: list) -> dict:
    out = {}
    ids = list(ids)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for pid, text in conn.execute(f"SELECT passage_id, text FROM passages WHERE passage_id IN ({marks})", chunk):
            out[pid] = text or ""
    return out


def french_subset(rows: list, french_qids: set, keys: list) -> dict:
    subset = [r for r in rows if r["qid"] in french_qids]
    return {"n_questions": len(subset), "aggregate": {k: mean4([r.get(k) for r in subset]) for k in keys} if subset else None}


def run_scope(name: str, *, rescore_n: int, skip_pool: bool, skip_paid: bool) -> dict:
    from archive_debugger.retrieve import dense
    from archive_debugger.retrieve.config import load_retrieve_config
    from archive_debugger.retrieve.embed import make_embedder
    from archive_debugger.retrieve.search import Retriever

    os.environ[dense.ENV_BACKEND] = "sqlite"     # the arms inject their own dense leg; no second load
    scope = scopes.resolve_scope(name)
    result: dict = {"scope": name, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "machine": {"platform": platform.platform(), "processor": platform.processor(),
                                "python": platform.python_version(), "numpy": np.__version__,
                                "cpu_count": os.cpu_count()},
                    "rescore_n": rescore_n, "arms": {}, "pool": {}}
    with scopes.activate(None if scope.inherit else scope):
        cfg = load_retrieve_config(scope.config_path)
        result["config"] = {"path": str(scope.config_path), "switches": cfg.switches(), "candidates": cfg.candidates,
                            "rrf_k": cfg.rrf_k, "embedding_model": cfg.embedding_model}
        conn = rundb.open_corpus_read_only(scope.db_path)
        gold = load_gold(conn)
        french_qids = {q["qid"] for q in gold if looks_french(q["text"])}
        result["gold"] = {"questions": len(gold), "answerable": sum(1 for q in gold if q["answerable"]),
                          "labels": sum(len(q["labels"]) for q in gold),
                          "relevant": sum(1 for q in gold for r in q["labels"].values() if r > 0),
                          "french_questions": sorted(french_qids)}
        log(f"[{name}] gold: {result['gold']}")
        embedder = CachedQueryEmbedder(make_embedder(cfg.embedder, cfg.embedding_model, cfg.embedding_dim))
        retriever = Retriever(None, cfg=cfg, embedder=embedder)
        try:
            log(f"[{name}] reading the float32 matrix from {scope.index_path}")
            t0 = time.perf_counter()
            (matrix, ids), f32_held, f32_peak = traced(lambda: dense.read_rows(retriever.conn))
            load_s = time.perf_counter() - t0
            n, dim = matrix.shape
            exact = dense.DenseIndex(matrix, ids)
            (codes, scale), i8_held, i8_peak = traced(lambda: quantize_int8_per_dim(matrix))
            packed, bin_held, bin_peak = traced(lambda: pack_signs(matrix))
            ids_bytes = n * 160  # retrieve.dense._ID_BYTES_PER_ROW, the measured per-row cost of ids + lookup
            result["index"] = {"rows": n, "dim": dim, "float32_load_seconds": round(load_s, 1)}
            result["memory"] = {
                "bm25_only": {"dense_bytes_arithmetic": 0, "note": "no dense vectors held"},
                "hybrid_exact": {"dense_bytes_arithmetic": n * dim * 4, "ids_bytes_estimate": ids_bytes,
                                 "measured_held_bytes_matrix_plus_ids": f32_held, "measured_peak_bytes": f32_peak,
                                 "matrix_nbytes": int(matrix.nbytes)},
                "hybrid_int8": {"dense_bytes_arithmetic": n * dim + dim * 4, "ids_bytes_estimate": ids_bytes,
                                "measured_held_bytes": i8_held, "measured_peak_bytes_during_build": i8_peak,
                                "codes_nbytes": int(codes.nbytes), "scale_nbytes": int(scale.nbytes)},
                "hybrid_binary_rescore": {"dense_bytes_arithmetic": n * ((dim + 7) // 8), "ids_bytes_estimate": ids_bytes,
                                          "measured_held_bytes": bin_held, "measured_peak_bytes_during_build": bin_peak,
                                          "rescore_float32_bytes_if_resident": n * dim * 4,
                                          "note": "rescoring reads rescore_n float32 rows per query; here the float "
                                                  "matrix was resident, it could be memory-mapped from disk instead"},
            }
            log(f"[{name}] rows={n} dim={dim}; memory {json.dumps(result['memory'])}")
            legs = {
                "bm25_only": None,
                "hybrid_exact": TimedDense(exact),
                "hybrid_int8": TimedDense(Int8DenseIndex(codes, scale, ids), reference=exact),
                "hybrid_binary_rescore": TimedDense(BinaryRescoreIndex(packed, matrix, ids, rescore_n), reference=exact),
            }
            original_dense = retriever._dense
            first = gold[0]
            for arm in ARMS:
                leg = legs[arm]
                if leg is None:
                    retriever._dense = lambda qvec, where, params, k: []  # type: ignore[method-assign]
                else:
                    retriever._dense = original_dense  # type: ignore[method-assign]
                    retriever.dense_index = leg
                timed = TimedSearch(retriever)
                timed.search(first["text"], filters=filters_from(first), top_k=TOP_N)   # warm-up, discarded
                timed.seconds = []
                if leg is not None:
                    leg.reset()
                t0 = time.perf_counter()
                rep = report.evaluate(conn, timed, recall_ks=list(RECALL_KS), ndcg_k=NDCG_K, min_relevant=1, top_n=TOP_N)
                keys = list(rep["aggregate"].keys())
                result["arms"][arm] = {
                    "aggregate": rep["aggregate"], "labeled": rep["labeled"], "per_question": rep["per_question"],
                    "french": french_subset(rep["per_question"], french_qids, keys),
                    "search_latency_excluding_query_embedding": latency_summary(timed.seconds),
                    "dense_leg_latency": latency_summary(leg.seconds) if leg is not None else None,
                    "dense_overlap_at_candidates_vs_exact": (mean4(leg.overlaps) if leg is not None and leg.overlaps else None),
                    "seconds": round(time.perf_counter() - t0, 1),
                }
                log(f"[{name}] {arm}: {rep['aggregate']} search {result['arms'][arm]['search_latency_excluding_query_embedding']}"
                    f" dense {result['arms'][arm]['dense_leg_latency']} overlap {result['arms'][arm]['dense_overlap_at_candidates_vs_exact']}")
            result["query_embedding_latency"] = latency_summary(list(embedder.seconds.values()))
        finally:
            retriever.close()
        conn.close()
    del legs, exact, codes, packed, matrix
    if not skip_pool:
        result["pool"] = run_pool_scope(name, skip_paid=skip_paid)
    return result


def stored_vectors(index_path: Path, ids: list) -> dict:
    """The production MiniLM vectors of the listed passages, read by id from the vectors database."""
    import sqlite3
    conn = sqlite3.connect(f"file:{Path(index_path).resolve().as_posix()}?mode=ro", uri=True)
    out = {}
    try:
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for pid, emb in conn.execute(f"SELECT passage_id, embedding FROM passages_vec WHERE passage_id IN ({marks})", chunk):
                out[pid] = np.frombuffer(emb, dtype=np.float32).copy()
    finally:
        conn.close()
    return out


def random_order_expectation(pool_size: int, n_relevant: int) -> dict:
    """Expected recall@k and nDCG@10 when a pool with n_relevant binary-relevant passages is put in a
    uniformly random order (exact, by linearity of expectation: each rank holds a relevant passage
    with probability n_relevant / pool_size). None when there is no relevant passage."""
    if n_relevant <= 0 or pool_size <= 0:
        return {**{f"recall@{k}": None for k in RECALL_KS}, f"ndcg@{NDCG_K}": None}
    out = {f"recall@{k}": min(k, pool_size) / pool_size for k in RECALL_KS}
    p = n_relevant / pool_size
    expected_dcg = sum(p / math.log2(i + 2) for i in range(min(NDCG_K, pool_size)))
    out[f"ndcg@{NDCG_K}"] = expected_dcg / metrics.dcg([1.0] * min(n_relevant, NDCG_K))
    return out


def run_pool_scope(name: str, *, skip_paid: bool) -> dict:
    from archive_debugger.retrieve.config import load_retrieve_config
    from archive_debugger.retrieve.embed import make_embedder

    scope = scopes.resolve_scope(name)
    with scopes.activate(None if scope.inherit else scope):
        cfg = load_retrieve_config(scope.config_path)
        conn = rundb.open_corpus_read_only(scope.db_path)
        try:
            gold = load_gold(conn)
            french_qids = {q["qid"] for q in gold if looks_french(q["text"])}
            pool_ids = sorted({pid for q in gold for pid in q["labels"]})
            stored = stored_vectors(scope.index_path, pool_ids)
            embedder = make_embedder(cfg.embedder, cfg.embedding_model, cfg.embedding_dim)
            query_minilm = {q["qid"]: np.asarray(embedder.embed_query(q["text"]), dtype=np.float32) for q in gold}
            return run_pool(name, conn, gold, pool_ids, stored, query_minilm, french_qids, skip_paid=skip_paid)
        finally:
            conn.close()


def run_pool(name: str, conn, gold: list, pool_ids: list, stored: dict, query_minilm: dict, french_qids: set,
             *, skip_paid: bool) -> dict:
    texts = passage_texts(conn, pool_ids)
    missing = [pid for pid in pool_ids if pid not in texts]
    out: dict = {"pool_passages": len(pool_ids), "pool_passages_missing_text": len(missing),
                 "pool_size_per_question": {"mean": round(sum(len(q["labels"]) for q in gold) / len(gold), 2),
                                            "min": min(len(q["labels"]) for q in gold),
                                            "max": max(len(q["labels"]) for q in gold)},
                 "pool_chars": sum(len(t) for t in texts.values()), "models": {}}
    keys = [f"recall@{k}" for k in RECALL_KS] + [f"ndcg@{NDCG_K}"]
    random_rows = [random_order_expectation(len(q["labels"]), sum(1 for r in q["labels"].values() if r > 0)) for q in gold]
    out["random_order_expected"] = {k: mean4([r[k] for r in random_rows]) for k in keys}
    log(f"[{name}] pool random-order expectation: {out['random_order_expected']}")
    ledger = Ledger(LEDGER_PATH)
    for model_name, kind, model_id, prefix, licence, max_tokens in POOL_MODELS:
        entry: dict = {"model": model_id, "kind": kind, "licence": licence, "max_input_tokens": max_tokens,
                       "query_prefix": prefix}
        try:
            if kind == "stored":
                passage_vecs, query_vecs = stored, query_minilm
                entry["note"] = "passages: the stored index vectors; questions: the production embedder"
            else:
                passage_list = [texts[pid] for pid in pool_ids if pid in texts]
                query_list = [prefix + q["text"] for q in gold]
                by_text, stats = embed_with_cache(model_name, kind, model_id, passage_list + query_list,
                                                  ledger=ledger, skip_paid=skip_paid)
                entry["embedding_calls"] = stats
                passage_vecs = {pid: by_text[texts[pid]] for pid in pool_ids if pid in texts}
                query_vecs = {q["qid"]: by_text[prefix + q["text"]] for q in gold}
            entry["dim"] = int(len(next(iter(passage_vecs.values()))))
            rows = []
            cos_relevant, cos_other = [], []
            for q in gold:
                pool = [pid for pid in q["labels"] if pid in passage_vecs]
                ranked = rank_pool(query_vecs[q["qid"]], pool, passage_vecs)
                rows.append({"qid": q["qid"], "answerable": q["answerable"], "pool_size": len(pool),
                             **pool_metrics(ranked, q["labels"])})
                qv = unit(query_vecs[q["qid"]])
                for pid in pool:
                    (cos_relevant if q["labels"][pid] > 0 else cos_other).append(float(unit(passage_vecs[pid]) @ qv))
            entry["aggregate"] = {k: mean4([r[k] for r in rows]) for k in keys}
            entry["mean_cosine_relevant"] = mean4(cos_relevant)
            entry["mean_cosine_not_relevant"] = mean4(cos_other)
            entry["per_question"] = rows
            entry["french"] = french_subset(rows, french_qids, keys)
            log(f"[{name}] pool {model_name}: {entry['aggregate']} cos rel {entry['mean_cosine_relevant']} "
                f"not {entry['mean_cosine_not_relevant']}")
        except RuntimeError as exc:
            if str(exc) != "skip-paid":
                raise
            entry["skipped"] = "paid model skipped (--skip-paid)"
        except BudgetExceeded as exc:
            entry["skipped"] = f"stopped by the budget: {exc}"
            log(f"[{name}] pool {model_name}: {entry['skipped']}")
        out["models"][model_name] = entry
    return out


def ledger_spend(run_id: str = RUN_ID) -> dict:
    by_model: dict = {}
    for e in iter_jsonl(LEDGER_PATH):
        if e.get("run_id") != run_id or e.get("kind") != "spend":
            continue
        row = by_model.setdefault(e["model"], {"calls": 0, "input_tokens": 0, "usd": 0.0, "estimated_calls": 0})
        row["calls"] += 1
        row["input_tokens"] += int(e.get("input_tokens") or 0)
        row["usd"] = round(row["usd"] + float(e["usd"]), 6)
        if "worst case" in (e.get("what") or ""):
            row["estimated_calls"] += 1
    return by_model


# --- report -------------------------------------------------------------------------------------------

def _f(v, digits: int = 4) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _mb(v) -> str:
    return "n/a" if v is None else f"{v / 1e6:,.1f} MB"


def write_report(scopes_done: dict) -> None:
    spend = ledger_spend()
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": RUN_ID,
               "run_cap_usd": RUN_CAP_USD, "workers_ai_spend_from_ledger": spend, "scopes": scopes_done}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Retrieval ablation (Phase 2 Part A)", "",
             f"Generated {payload['generated']} by scripts/v2/retrieval_ablation.py. No answer-model calls.", "",
             "Corpus-wide arms run the production Retriever with the scope's config as it is; only the dense",
             "leg changes. Gold is the v1 gold stored in each corpus database. Pooled values: a ranking that",
             "surfaces passages nobody judged cannot be credited for them, so read unjudged@10 beside recall.",
             "Latency is on the local development machine (see machine in the JSON), one pass per arm after",
             "one warm-up query, question embeddings cached so search timings exclude them. int8 uses one",
             "symmetric scale per dimension and scores the codes directly; binary keeps sign bits, takes the",
             "Hamming-nearest rescore_n rows, then rescores them with float32 cosine.", ""]
    for name, res in scopes_done.items():
        g = res["gold"]
        lines += [f"## {name}", "",
                  f"Gold: {g['questions']} labeled questions ({g['answerable']} answerable), {g['labels']} labels, "
                  f"{g['relevant']} relevant. French questions in the gold: {len(g['french_questions'])}"
                  + (f" ({', '.join(g['french_questions'])})" if g['french_questions'] else " (no French subset to report)") + ".",
                  f"Dense index: {res['index']['rows']:,} rows x {res['index']['dim']} dims; binary rescore_n = {res['rescore_n']}.", "",
                  "| arm | recall@5 | recall@10 | recall@20 | ndcg@10 | unjudged@10 | unjudged@20 | dense overlap vs exact |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for arm, a in res["arms"].items():
            ag = a["aggregate"]
            lines.append(f"| {arm} | {_f(ag.get('recall@5'))} | {_f(ag.get('recall@10'))} | {_f(ag.get('recall@20'))} | "
                         f"{_f(ag.get('ndcg@10'))} | {_f(ag.get('unjudged@10'))} | {_f(ag.get('unjudged@20'))} | "
                         f"{_f(a['dense_overlap_at_candidates_vs_exact'])} |")
        lines += ["", "| arm | dense bytes (rows x dim arithmetic) | measured held (tracemalloc) | dense leg median / p95 ms | search median / p95 ms |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for arm, a in res["arms"].items():
            mem = res["memory"][arm]
            held = mem.get("measured_held_bytes", mem.get("measured_held_bytes_matrix_plus_ids"))
            dl = a["dense_leg_latency"] or {}
            sl = a["search_latency_excluding_query_embedding"]
            lines.append(f"| {arm} | {_mb(mem['dense_bytes_arithmetic'])} | {_mb(held)} | "
                         f"{_f(dl.get('median_ms'), 1)} / {_f(dl.get('p95_ms'), 1)} | {_f(sl['median_ms'], 1)} / {_f(sl['p95_ms'], 1)} |")
        qe = res.get("query_embedding_latency") or {}
        lines += ["", f"Question embedding (MiniLM, local): median {_f(qe.get('median_ms'), 1)} ms, p95 {_f(qe.get('p95_ms'), 1)} ms. "
                  "The float32 held figure includes the passage-id list; the binary arm also needs float32 rows for rescoring.", ""]
        pool = res.get("pool") or {}
        if pool.get("models"):
            ps = pool["pool_size_per_question"]
            lines += [f"Pool re-ranking: {pool['pool_passages']} judged passages, per question mean {ps['mean']} "
                      f"(min {ps['min']}, max {ps['max']}). Every ranked passage is judged.", "",
                      "| embedder | dim | licence | recall@5 | recall@10 | recall@20 | ndcg@10 | mean cos relevant / not (all questions pooled) |",
                      "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
            rnd = pool.get("random_order_expected") or {}
            lines.append(f"| random order (expected) | | | {_f(rnd.get('recall@5'))} | {_f(rnd.get('recall@10'))} | "
                         f"{_f(rnd.get('recall@20'))} | {_f(rnd.get('ndcg@10'))} | |")
            for model_name, m in pool["models"].items():
                if "aggregate" not in m:
                    lines.append(f"| {model_name} ({m['model']}) | | {m['licence']} | {m.get('skipped', 'not run')} | | | | |")
                    continue
                ag = m["aggregate"]
                lines.append(f"| {model_name} ({m['model']}) | {m['dim']} | {m['licence']} | {_f(ag['recall@5'])} | "
                             f"{_f(ag['recall@10'])} | {_f(ag['recall@20'])} | {_f(ag['ndcg@10'])} | "
                             f"{_f(m.get('mean_cosine_relevant'), 3)} / {_f(m.get('mean_cosine_not_relevant'), 3)} |")
            lines += ["", "The pool is the judged passages, which were gathered from the production retriever's own",
                      "top results, BM25 + MiniLM fused (pilot: top-30 plus the Phase 13 extension; microlog: the",
                      "top-10 of a 30-pool, so with at most 10 passages recall@10 is 1.0 for any order and only",
                      "recall@5 and nDCG@10 separate the embedders). MiniLM helped choose which non-relevant passages entered the",
                      "pool, so within the pool it is measured against its own false positives; the other embedders",
                      "are not. Read the MiniLM row as a pool-selection effect, not as MiniLM's corpus-wide quality.", ""]
    lines += ["## Workers AI spend (ledger, run " + RUN_ID + f", cap ${RUN_CAP_USD:.2f})", "",
              "| model | calls | input tokens | usd | calls with estimated usage |", "| --- | ---: | ---: | ---: | ---: |"]
    for model, row in spend.items():
        lines.append(f"| {model} | {row['calls']} | {row['input_tokens']:,} | {row['usd']:.6f} | {row['estimated_calls']} |")
    if not spend:
        lines.append("| none | 0 | 0 | 0 | 0 |")
    OUT_MD.write_text(NEWLINE.join(lines) + NEWLINE, encoding="utf-8")


def assemble() -> dict:
    done = {}
    for name in ("pilot", "microlog"):
        path = RAW_DIR / f"{name}.json"
        if path.exists():
            done[name] = json.loads(path.read_text(encoding="utf-8"))
    if done:
        write_report(done)
    return done


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    p = argparse.ArgumentParser(description="Retrieval ablation over the v1 gold (no answer-model calls).")
    p.add_argument("--scope", action="append", choices=["pilot", "microlog"], default=None)
    p.add_argument("--rescore", type=int, default=DEFAULT_RESCORE, help="binary arm: Hamming candidates rescored in float32")
    p.add_argument("--skip-pool", action="store_true")
    p.add_argument("--skip-paid", action="store_true", help="no Workers AI calls")
    p.add_argument("--pool-only", action="store_true", help="recompute only the pool arms into an existing checkpoint")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    os.chdir(REPO)
    if args.pool_only:
        for name in args.scope or ["pilot", "microlog"]:
            path = RAW_DIR / f"{name}.json"
            res = json.loads(path.read_text(encoding="utf-8"))
            res["pool"] = run_pool_scope(name, skip_paid=args.skip_paid)
            path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"[{name}] pool arms rewritten in {path}")
    elif not args.report_only:
        for name in args.scope or ["pilot", "microlog"]:
            res = run_scope(name, rescore_n=args.rescore, skip_pool=args.skip_pool, skip_paid=args.skip_paid)
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"[{name}] checkpoint written to {RAW_DIR / (name + '.json')}")
    assemble()
    log(f"report: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
