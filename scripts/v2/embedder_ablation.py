"""Phase 3 embedder ablation: candidate dense embedders compared on one shared sub-corpus per
collection, pooled relevance-judgment items for the audit panel, and scores once judgments exist.

Why a sub-corpus. Embedding a whole collection once per candidate is too slow locally and too
dear through Workers AI, and gathering candidates with one embedder would favour it. So each
collection gets one sub-corpus that no embedder had a hand in: the union of the BM25 top
--bm25-depth passages per question over the full collection (the production FTS query, built by
Retriever._fts_query itself, the question's filters applied, ORDER BY rank), a seeded random
--distractors passages from the rest of the collection, and every question's source passages.
The passage id list and its sha256 go to <out>/<collection>/subcorpus.json. A later run with the
same questions and parameters reuses that list, so every candidate searches exactly the same
passages.

Questions come from the benchmark split files named by --questions (default the dev and
validation splits of reports/v2/benchmark/v2). Items whose label says the system should refuse,
and items with no question, are dropped; --per-collection caps each collection with a seeded
sample. A test split is never read: a path whose file name contains "test" is refused.

Candidates (name, model, where it runs):
  minilm-128            paraphrase-multilingual-MiniLM-L12-v2 through fastembed, its default
                        128-token truncation (the production embedder)
  minilm-256            the same model with the tokenizer's truncation raised to 256
  minilm-512            the same model with the tokenizer's truncation raised to 512 (measured at
                        3.5 passages a second on the laptop CPU, about 150 CPU-hours for the current
                        index: run only with --candidates when that time is acceptable)
  minilm-chunks         the same model over windows of at most 128 model tokens (32 tokens of
                        overlap); a passage scores the best cosine of any of its windows
  bge-m3                @cf/baai/bge-m3 on Workers AI (paid)
  qwen3-embedding-0.6b  @cf/qwen/qwen3-embedding-0.6b on Workers AI (paid), with the model's
                        instruction prefix on questions
  arctic-embed-m-v2.0   Snowflake/snowflake-arctic-embed-m-v2.0 locally, only when the installed
                        fastembed lists it; otherwise it is recorded as BLOCKED with the reason
Workers AI inputs are cut to 2000 characters. Every Workers AI call reserves its worst case in the
audit ledger under --run-id and --cap (and the phase cap from config/audit.toml) before it is
made, through the metered loop in retrieval_ablation.py. --skip-paid makes no paid call.

Every embedding matrix is cached per candidate and collection as .npy plus an ids file, keyed by
the sub-corpus sha256, and written in blocks so an interrupted run resumes where it stopped; a
rerun never embeds the same passages twice. Question vectors are cached the same way. Embedding
wall time, rows, and the median and p95 latency of embedding one question are recorded.

Systems, all over the sub-corpus only, with the question's filters (period such as "1980s",
"pre-1960", "post-2009" or "undated", and jurisdiction; the production filter predicates) applied
to every system identically before ranking:
  bm25                  the FTS ranking restricted to the sub-corpus, top 50
  dense <candidate>     cosine over the sub-corpus, top 50
  hybrid <candidate>    reciprocal rank fusion (k from the retrieve config, 60) of the top 200 of
                        the BM25 and dense rankings, top 10

The pool for a question is the union of every system's top 10. One judge item per (question,
passage), kind "relevance" (audit/prompts.py), goes to pool_items.jsonl, and every ranking to
rankings.json, both per collection and assembled at the top of --out.

The score subcommand reads one or more audit runs (reports/v2/audit/runs/<run>/panel.jsonl; a
later run's decision on an item replaces an earlier one) and computes per system recall@10 (a
passage is relevant when the panel's final verdict is pass; the denominator is the pooled
passages judged pass for that question; questions with none are left out and counted), nDCG@10
(gain 2 for pass, 1 for partial, 0 otherwise), the share of each top 10 left unjudged or sent to a
person, and paired bootstrap 95% intervals (2000 resamples over questions, seeded) for each
system's difference from "hybrid minilm-128", per collection and pooled. It also reports each
candidate's stored index size for the whole collection by arithmetic (corpus rows x dim x 4 bytes
for float32, x 1 byte for int8, dim / 8 bytes for sign bits), and with --spot N draws a seeded
random sample of pool items for the reference judges (spot_items.jsonl).

A heavy-job lock, .cc-heavy.lock in the repo root, is taken before build does any work and removed
when it ends, also on error. When another job holds it, build prints a message and exits with
status 3.

Run:
    .venv/Scripts/python.exe scripts/v2/embedder_ablation.py build --collections pilot microlog --run-id embed-ablation-1 --cap 2.00
    .venv/Scripts/python.exe scripts/v2/embedder_ablation.py score --runs relevance-panel-1 --spot 100

Writes under --out (default reports/v2/raw/embedder_ablation):
    <collection>/subcorpus.json, <collection>/embeddings/*, <collection>/rankings.json,
    <collection>/pool_items.jsonl, <collection>/build.json,
    pool_items.jsonl, rankings.json, scores.json, scores.md, spot_items.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location("retrieval_ablation", Path(__file__).resolve().parent / "retrieval_ablation.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

from archive_debugger.audit import calibration, prices  # noqa: E402
from archive_debugger.audit.budget import BudgetExceeded, Ledger  # noqa: E402
from archive_debugger.audit.records import iter_jsonl, read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.eval import metrics  # noqa: E402
from archive_debugger.retrieve.filters import Filters, build_where  # noqa: E402
from archive_debugger.retrieve.fusion import rrf  # noqa: E402

NEWLINE = chr(10)
DEFAULT_OUT = REPO / "reports" / "v2" / "raw" / "embedder_ablation"
DEFAULT_QUESTIONS = (REPO / "reports" / "v2" / "benchmark" / "v2" / "dev.jsonl",
                     REPO / "reports" / "v2" / "benchmark" / "v2" / "validation.jsonl")
RUNS_DIR = REPO / "reports" / "v2" / "audit" / "runs"
LOCK_PATH = REPO / ".cc-heavy.lock"
LEDGER_PATH = REPO / "reports" / "v2" / "audit" / "ledger.jsonl"
IAC_PAGES = 22_100_000      # about 22.1 million scanned pages in the whole collection (archive.org)
LOCK_OWNER = "run-A embedder_ablation"
LOCK_BUSY_STATUS = 3

DEFAULT_RRF_K = 60
FUSION_DEPTH = 200          # each leg's candidates fed into RRF, as the production config's candidates
DENSE_TOP = 50
HYBRID_TOP = 10
POOL_TOP = 10
BLOCK_ROWS = 2048           # rows embedded and saved per part file
WORKERS_AI_CHARS = 2000
CHUNK_TOKENS = 128
CHUNK_OVERLAP = 32
BOOTSTRAP = 2000
RERANKER = "@cf/baai/bge-reranker-base"
RERANK_DEPTH = 30          # fused passages the reranker reorders
RERANK_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
BINARY_SHORTLIST = 400      # rows the sign bits pass to the int8 rerank (compact storage)
REFERENCE_SYSTEM = "hybrid minilm-128"
GAIN = {"pass": 2, "partial": 1, "fail": 0}

MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ARCTIC_V2 = "Snowflake/snowflake-arctic-embed-m-v2.0"
ARCTIC_V2_QUERY_PREFIX = "query: "


def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- the heavy-job lock -----------------------------------------------------------------------------

class LockBusy(Exception):
    pass


class HeavyLock:
    """.cc-heavy.lock holds one line naming its owner and when it was taken. A lock this script
    left behind (same owner prefix) is taken over; anyone else's lock refuses the run."""

    def __init__(self, path: Path = LOCK_PATH, owner: str = LOCK_OWNER):
        self.path = Path(path)
        self.owner = owner
        self.held = False

    def __enter__(self):
        if self.path.exists():
            content = self.path.read_text(encoding="utf-8", errors="replace").strip()
            if not content.startswith(self.owner):
                raise LockBusy(f"{self.path} is held by another job: {content!r}")
        self.path.write_text(f"{self.owner} {now_iso()}" + NEWLINE, encoding="utf-8")
        self.held = True
        return self

    def __exit__(self, *exc):
        if self.held and self.path.exists():
            self.path.unlink()
        self.held = False
        return False


# --- questions --------------------------------------------------------------------------------------

def refuse_test_split(path: Path) -> None:
    if "test" in Path(path).name.lower():
        raise ValueError(f"refused: {path} looks like a test split, which this experiment never reads")


def load_questions(paths, per_collection: Optional[int], seed: int, collections_wanted=None) -> dict:
    """{collection: [question item, ...]} sorted by item id: answerable items (should_refuse false)
    with a question, at most per_collection per collection by a seeded sample."""
    by_collection: dict = {}
    for path in paths:
        refuse_test_split(path)
        for item in read_jsonl(path):
            if (item.get("label") or {}).get("should_refuse") is not False:
                continue
            if not (item.get("question") or "").strip():
                continue
            if collections_wanted and item.get("collection") not in collections_wanted:
                continue
            by_collection.setdefault(item["collection"], {})[item["item_id"]] = item
    out = {}
    for name in sorted(by_collection):
        members = [by_collection[name][k] for k in sorted(by_collection[name])]
        if per_collection is not None and per_collection < len(members):
            members = random.Random(f"questions:{seed}:{name}").sample(members, per_collection)
            members.sort(key=lambda it: it["item_id"])
        out[name] = members
    return out


def question_filters(item: dict) -> Filters:
    f = item.get("filters") or {}
    return Filters(period=f.get("period") or None, jurisdiction=f.get("jurisdiction") or None)


def source_ids(item: dict) -> list:
    return [s["passage_id"] for s in item.get("sources") or [] if s.get("passage_id")]


# --- corpus access ----------------------------------------------------------------------------------

def fts_query(query: str, drop_stopwords: bool = True) -> str:
    """The production FTS5 query string, built by Retriever._fts_query itself."""
    from archive_debugger.retrieve.search import Retriever
    return Retriever._fts_query(SimpleNamespace(cfg=SimpleNamespace(fts_drop_stopwords=drop_stopwords)), query)


def bm25_ranking(conn, query: str, filters: Filters, k: int, *, within: Optional[list] = None,
                 drop_stopwords: bool = True) -> list:
    """Passage ids by FTS5 rank, best first (ties by passage id), the filter applied in SQL. With
    within, only those passages are ranked."""
    where, params = build_where(filters)
    restrict = ""
    restrict_params: list = []
    if within is not None:
        restrict = " AND p.passage_id IN (SELECT value FROM json_each(?))"
        restrict_params = [json.dumps(list(within))]
    sql = ("SELECT p.passage_id FROM passages_fts f "
           "JOIN passages p ON p.rowid = f.rowid "
           "JOIN items i ON i.item_id = p.item_id "
           "WHERE passages_fts MATCH ?" + where + restrict +
           " ORDER BY rank, p.passage_id LIMIT ?")
    return [r[0] for r in conn.execute(sql, [fts_query(query, drop_stopwords), *params, *restrict_params, k])]


def allowed_ids(conn, filters: Filters, within: list) -> set:
    """The passages among within that the filter allows (the production predicate)."""
    where, params = build_where(filters)
    if not where:
        return set(within)
    sql = ("SELECT p.passage_id FROM passages p JOIN items i ON i.item_id = p.item_id "
           "WHERE p.passage_id IN (SELECT value FROM json_each(?))" + where)
    return {r[0] for r in conn.execute(sql, [json.dumps(list(within)), *params])}


def all_passage_ids(conn) -> list:
    return sorted(r[0] for r in conn.execute("SELECT passage_id FROM passages"))


def passage_rows(conn, ids: list) -> dict:
    """{passage_id: metadata and text} for the listed passages."""
    out = {}
    ids = list(ids)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        sql = ("SELECT p.passage_id, p.item_id, p.leaf_index, p.text, i.title, i.year, i.jurisdiction_norm "
               "FROM passages p LEFT JOIN items i ON i.item_id = p.item_id "
               f"WHERE p.passage_id IN ({marks})")
        for pid, item_id, leaf, text, title, year, jur in conn.execute(sql, chunk):
            out[pid] = {"passage_id": pid, "item_id": item_id, "leaf_index": leaf, "text": text or "",
                        "title": title, "year": year, "jurisdiction": jur}
    return out


def ids_digest(ids: list) -> str:
    return hashlib.sha256(NEWLINE.join(ids).encode("utf-8")).hexdigest()


def make_subcorpus(conn, collection: str, questions: list, *, bm25_depth: int, distractors: int, seed: int,
                   drop_stopwords: bool = True) -> dict:
    """The shared sub-corpus: BM25 hits over the full collection, sources, and seeded distractors."""
    corpus_ids = all_passage_ids(conn)
    known = set(corpus_ids)
    bm25_hits: set = set()
    for q in questions:
        bm25_hits.update(bm25_ranking(conn, q["question"], question_filters(q), bm25_depth,
                                      drop_stopwords=drop_stopwords))
    sources = {pid for q in questions for pid in source_ids(q) if pid in known}
    missing_sources = sorted({pid for q in questions for pid in source_ids(q)} - known)
    chosen = bm25_hits | sources
    rest = [pid for pid in corpus_ids if pid not in chosen]
    rng = random.Random(f"distractors:{seed}:{collection}")
    picked = rng.sample(rest, min(distractors, len(rest)))
    ids = sorted(chosen | set(picked))
    return {"format": 1, "collection": collection, "corpus_rows": len(corpus_ids),
            "counts": {"bm25_hits": len(bm25_hits), "sources": len(sources), "distractors": len(picked),
                       "total": len(ids)},
            "missing_sources": missing_sources, "sha256": ids_digest(ids), "passage_ids": ids}


def subcorpus_params(questions: list, bm25_depth: int, distractors: int, seed: int, drop_stopwords: bool) -> dict:
    return {"bm25_depth": bm25_depth, "distractors": distractors, "seed": seed, "drop_stopwords": drop_stopwords,
            "questions": [q["item_id"] for q in questions],
            "question_texts_sha256": ids_digest([q["question"] for q in questions])}


def load_or_make_subcorpus(conn, collection: str, questions: list, coll_dir: Path, **params) -> dict:
    wanted = subcorpus_params(questions, params["bm25_depth"], params["distractors"], params["seed"],
                              params["drop_stopwords"])
    path = coll_dir / "subcorpus.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("params") == wanted and ids_digest(existing["passage_ids"]) == existing["sha256"]:
            log(f"[{collection}] sub-corpus reused: {existing['counts']}")
            return existing
    sub = make_subcorpus(conn, collection, questions, **params)
    sub["params"] = wanted
    sub["built"] = now_iso()
    coll_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sub, indent=1, sort_keys=True), encoding="utf-8")
    log(f"[{collection}] sub-corpus built: {sub['counts']} sha256 {sub['sha256'][:16]}")
    return sub


# --- encoders ---------------------------------------------------------------------------------------
# An encoder has embed(texts) -> (n, dim) float32 and, for a chunked candidate, windows(text) -> the
# texts its windows cover. Tests inject their own in place of fastembed and Workers AI.

class FastEmbedEncoder:
    def __init__(self, model: str, max_tokens: Optional[int] = None):
        from fastembed import TextEmbedding
        self.model = model
        self.engine = TextEmbedding(model_name=model)
        self.max_tokens = max_tokens
        if max_tokens is not None:
            self.engine.model.tokenizer.enable_truncation(max_length=max_tokens)

    def truncation(self) -> dict:
        return dict(self.engine.model.tokenizer.truncation or {})

    def embed(self, texts: list) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([np.asarray(v, dtype=np.float32) for v in self.engine.embed(list(texts), batch_size=64)])


def window_spans(n_tokens: int, width: int, overlap: int) -> list:
    """(start, end) token spans of at most width tokens, each overlapping the last by overlap
    tokens, covering 0..n_tokens. A text with no tokens has one empty span."""
    if width <= 0 or overlap < 0 or overlap >= width:
        raise ValueError("need width > overlap >= 0")
    if n_tokens <= 0:
        return [(0, 0)]
    spans = []
    step = width - overlap
    start = 0
    while True:
        end = min(start + width, n_tokens)
        spans.append((start, end))
        if end >= n_tokens:
            return spans
        start += step


class ChunkedFastEmbedEncoder(FastEmbedEncoder):
    """The model at its own 128-token truncation over windows of at most CHUNK_TOKENS model tokens
    (special tokens included) cut from an untruncated copy of its tokenizer."""

    def __init__(self, model: str, window_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP):
        super().__init__(model)
        from tokenizers import Tokenizer
        tok = self.engine.model.tokenizer
        self.splitter = Tokenizer.from_str(tok.to_str())
        self.splitter.no_truncation()
        self.splitter.no_padding()
        self.width = window_tokens - self.splitter.num_special_tokens_to_add(False)
        self.overlap = overlap

    def windows(self, text: str) -> list:
        enc = self.splitter.encode(text or "", add_special_tokens=False)
        offsets = enc.offsets
        if not offsets:
            return [text or ""]
        return [text[offsets[s][0]:offsets[e - 1][1]] for s, e in window_spans(len(offsets), self.width, self.overlap)]


class WorkersAIEncoder:
    """Workers AI embeddings through retrieval_ablation.embed_workers_ai: worst case reserved in the
    ledger before every call, inputs cut to WORKERS_AI_CHARS characters."""

    def __init__(self, model: str, *, ledger: Ledger, run_id: str, run_cap: float, post: Optional[Callable] = None,
                 account: Optional[str] = None, headers: Optional[dict] = None):
        if post is None:
            from archive_debugger.audit import net
            post = net.post_json
        if account is None or headers is None:
            account, token = ra.judges.workers_ai_credentials()
            headers = ra.judges.workers_ai_headers(token, ra._gateway_name())
        self.model, self.ledger, self.run_id, self.run_cap = model, ledger, run_id, run_cap
        self.post, self.account, self.headers = post, account, headers
        self.usd = 0.0
        self.calls = 0

    def embed(self, texts: list) -> np.ndarray:
        cut = [(t or "")[:WORKERS_AI_CHARS] or " " for t in texts]
        result = ra.embed_workers_ai(self.model, cut, ledger=self.ledger, post=self.post, account=self.account,
                                     headers=self.headers, run_id=self.run_id, run_cap=self.run_cap)
        self.usd += result["usd"]
        self.calls += result["calls"]
        return np.stack(result["vectors"]).astype(np.float32)


@dataclass
class Candidate:
    name: str
    model: str
    dim: Optional[int]
    licence: str
    runs_on: str
    make: Optional[Callable[[], object]] = None
    paid: bool = False
    chunked: bool = False
    query_prefix: str = ""
    query_prefix_note: str = "none (the model takes the question as it is)"
    input_note: str = ""
    blocked: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {"name": self.name, "model": self.model, "dim": self.dim, "licence": self.licence,
                "runs_on": self.runs_on, "paid": self.paid, "chunked": self.chunked,
                "query_prefix": self.query_prefix, "query_prefix_note": self.query_prefix_note,
                "input_note": self.input_note, **self.extra}


def fastembed_supports(model: str) -> bool:
    from fastembed import TextEmbedding
    return any(m["model"].lower() == model.lower() for m in TextEmbedding.list_supported_models())


def default_candidates(*, ledger_factory: Callable[[], Ledger], run_id: str, run_cap: float) -> list:
    cands = [
        Candidate("minilm-128", MINILM, 384, "Apache-2.0", "local (fastembed)",
                  make=lambda: FastEmbedEncoder(MINILM), input_note="fastembed default truncation, 128 tokens"),
        Candidate("minilm-256", MINILM, 384, "Apache-2.0", "local (fastembed)",
                  make=lambda: FastEmbedEncoder(MINILM, max_tokens=256),
                  input_note="tokenizer truncation raised to 256 tokens (enable_truncation)"),
        Candidate("minilm-512", MINILM, 384, "Apache-2.0", "local (fastembed)",
                  make=lambda: FastEmbedEncoder(MINILM, max_tokens=512),
                  input_note="tokenizer truncation raised to 512 tokens (enable_truncation)"),
        Candidate("minilm-chunks", MINILM, 384, "Apache-2.0", "local (fastembed)",
                  make=lambda: ChunkedFastEmbedEncoder(MINILM), chunked=True,
                  input_note=f"windows of at most {CHUNK_TOKENS} model tokens, overlap {CHUNK_OVERLAP}; "
                             "passage score = max cosine over its windows"),
        Candidate("bge-m3", "@cf/baai/bge-m3", 1024, "MIT", "Workers AI (paid, metered)", paid=True,
                  make=lambda: WorkersAIEncoder("@cf/baai/bge-m3", ledger=ledger_factory(), run_id=run_id,
                                                run_cap=run_cap),
                  input_note=f"input cut to {WORKERS_AI_CHARS} characters"),
        Candidate("qwen3-embedding-0.6b", "@cf/qwen/qwen3-embedding-0.6b", 1024, "Apache-2.0",
                  "Workers AI (paid, metered)", paid=True,
                  make=lambda: WorkersAIEncoder("@cf/qwen/qwen3-embedding-0.6b", ledger=ledger_factory(),
                                                run_id=run_id, run_cap=run_cap),
                  query_prefix=ra.QWEN_QUERY_PREFIX,
                  query_prefix_note="the model card's instruction prefix on questions, none on passages",
                  input_note=f"input cut to {WORKERS_AI_CHARS} characters"),
    ]
    arctic = Candidate("arctic-embed-m-v2.0", ARCTIC_V2, 768, "Apache-2.0", "local (fastembed)",
                       query_prefix=ARCTIC_V2_QUERY_PREFIX,
                       query_prefix_note="the model card's query prefix on questions, none on passages")
    try:
        supported = fastembed_supports(ARCTIC_V2)
        reason = None if supported else "the installed fastembed does not list this model; nothing was installed"
    except ImportError as exc:
        supported, reason = False, f"fastembed is not importable: {exc}"
    if supported:
        arctic.make = lambda: FastEmbedEncoder(ARCTIC_V2)
    else:
        arctic.blocked = reason
    cands.append(arctic)
    return cands


# --- cached embeddings ------------------------------------------------------------------------------

def _save_npy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        np.save(fh, np.asarray(array, dtype=np.float32), allow_pickle=False)
    os.replace(tmp, path)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def unit_rows(matrix: np.ndarray) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def embed_cached(base: Path, key: dict, texts: list, encoder, *, block_rows: int = BLOCK_ROWS) -> tuple:
    """(matrix, stats) for texts, from base.npy when its key matches; otherwise embedded block by
    block, each block saved as a part file so an interrupted run resumes, then joined."""
    final, meta_path = base.with_name(base.name + ".npy"), base.with_name(base.name + ".json")
    if final.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("key") == key and meta.get("rows") == len(texts):
            return np.load(final, allow_pickle=False), dict(meta.get("stats") or {}, from_cache=True)
    progress_path = base.with_name(base.name + ".progress.json")
    progress = {}
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress.get("key") != key or progress.get("rows") != len(texts) or progress.get("block_rows") != block_rows:
            progress = {}
    seconds = float(progress.get("seconds") or 0.0)
    parts = []
    for n, start in enumerate(range(0, len(texts), block_rows)):
        part = base.with_name(f"{base.name}.part{n:05d}.npy")
        if progress and part.exists():
            parts.append(part)
            continue
        t0 = time.perf_counter()
        block = encoder.embed(texts[start:start + block_rows])
        seconds += time.perf_counter() - t0
        _save_npy(part, block)
        parts.append(part)
        progress = {"key": key, "rows": len(texts), "block_rows": block_rows, "seconds": round(seconds, 3)}
        _write_json(progress_path, progress)
    matrix = np.concatenate([np.load(p, allow_pickle=False) for p in parts]) if parts else np.zeros((0, 0), np.float32)
    stats = {"rows": int(matrix.shape[0]), "dim": int(matrix.shape[1]) if matrix.ndim == 2 else 0,
             "embed_seconds": round(seconds, 3), "from_cache": False}
    _save_npy(final, matrix)
    _write_json(meta_path, {"key": key, "rows": len(texts), "stats": stats})
    for p in parts:
        p.unlink()
    if progress_path.exists():
        progress_path.unlink()
    return matrix, stats


def passage_matrix(cand: Candidate, encoder, sub: dict, texts_by_id: dict, emb_dir: Path) -> tuple:
    """(unit matrix, owner row of each matrix row in the sub-corpus order, stats). Without chunks
    row i is sub-corpus passage i."""
    ids = sub["passage_ids"]
    base = emb_dir / f"{cand.name}-{sub['sha256'][:16]}"
    if cand.chunked:
        owners, texts = [], []
        for row, pid in enumerate(ids):
            for w in encoder.windows(texts_by_id[pid]):
                owners.append(row)
                texts.append(w)
    else:
        owners = list(range(len(ids)))
        texts = [texts_by_id[pid] for pid in ids]
    ids_path = base.with_name(base.name + ".ids.json")
    _write_json(ids_path, {"candidate": cand.name, "model": cand.model, "subcorpus_sha256": sub["sha256"],
                           "row_passage_ids": [ids[r] for r in owners]})
    key = {"candidate": cand.name, "model": cand.model, "subcorpus_sha256": sub["sha256"], "kind": "passages",
           "texts_sha256": ids_digest([hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts])}
    matrix, stats = embed_cached(base, key, texts, encoder)
    stats["passages"] = len(ids)
    stats["windows_per_passage"] = round(len(owners) / len(ids), 4) if ids else None
    return unit_rows(matrix), np.asarray(owners, dtype=np.int64), stats


def query_matrix(cand: Candidate, encoder, questions: list, emb_dir: Path, sha: str) -> tuple:
    """(unit query vectors in question order, stats with the per-question latency). Each question is
    embedded alone, so the latency is one question's; cached with its latencies."""
    texts = [cand.query_prefix + q["question"] for q in questions]
    base = emb_dir / f"{cand.name}-{sha[:16]}.queries"
    final, meta_path = base.with_name(base.name + ".npy"), base.with_name(base.name + ".json")
    key = {"candidate": cand.name, "model": cand.model, "kind": "queries", "texts_sha256": ids_digest(texts)}
    if final.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("key") == key:
            return unit_rows(np.load(final, allow_pickle=False)), dict(meta["stats"], from_cache=True)
    vectors, seconds = [], []
    for text in texts:
        t0 = time.perf_counter()
        vectors.append(encoder.embed([text])[0])
        seconds.append(time.perf_counter() - t0)
    matrix = np.stack(vectors).astype(np.float32) if vectors else np.zeros((0, 0), np.float32)
    stats = {"questions": len(texts), "latency": ra.latency_summary(seconds), "from_cache": False}
    _save_npy(final, matrix)
    _write_json(meta_path, {"key": key, "stats": stats})
    return unit_rows(matrix), stats


# --- systems ----------------------------------------------------------------------------------------

def dense_ranking(matrix: np.ndarray, owners: np.ndarray, qvec: np.ndarray, ids: list, allowed_mask: np.ndarray,
                  k: int) -> list:
    """Sub-corpus passage ids by cosine, best first (ties by sub-corpus order), only allowed rows.
    With windows, a passage's score is the best of its windows (max-sim)."""
    sims = matrix @ np.asarray(qvec, dtype=np.float32)
    scores = np.full(len(ids), -np.inf, dtype=np.float32)
    np.maximum.at(scores, owners, sims)
    scores[~allowed_mask] = -np.inf
    n_allowed = int(allowed_mask.sum())
    order = ra.top_k_desc(scores, min(k, n_allowed))
    return [ids[i] for i in order]


def fuse(rank_lists: list, k: int, top: int) -> list:
    """Reciprocal rank fusion (retrieve.fusion.rrf), best first, ties by passage id."""
    scores = rrf(rank_lists, k=k)
    return [pid for pid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))][:top]


def pool_item(collection: str, question: dict, row: dict) -> dict:
    return {"format": 1, "kind": "relevance",
            "item_id": f"{collection}:{question['item_id']}:{row['passage_id']}",
            "collection": collection, "qid": question["item_id"], "question": question["question"],
            "filters": question.get("filters") or {},
            "passage": {"passage_id": row["passage_id"], "item_id": row["item_id"], "title": row["title"],
                        "year": row["year"], "jurisdiction": row["jurisdiction"], "leaf_index": row["leaf_index"],
                        "deep_link": f"https://archive.org/details/{row['item_id']}/page/n{row['leaf_index']}",
                        "text": row["text"]},
            "writer_model": None}


def pool_items(collection: str, questions: list, rankings: dict, rows: dict, top: int = POOL_TOP) -> list:
    out = []
    for q in questions:
        pooled = set()
        for system in rankings.values():
            pooled.update(system.get(q["item_id"], [])[:top])
        out.extend(pool_item(collection, q, rows[pid]) for pid in sorted(pooled))
    return out


def build_collection(conn, collection: str, questions: list, candidates: list, *, out_dir: Path, bm25_depth: int,
                     distractors: int, seed: int, skip_paid: bool, rrf_k: int = DEFAULT_RRF_K,
                     drop_stopwords: bool = True) -> dict:
    coll_dir = Path(out_dir) / collection
    emb_dir = coll_dir / "embeddings"
    sub = load_or_make_subcorpus(conn, collection, questions, coll_dir, bm25_depth=bm25_depth,
                                 distractors=distractors, seed=seed, drop_stopwords=drop_stopwords)
    ids = sub["passage_ids"]
    rows = passage_rows(conn, ids)
    texts_by_id = {pid: rows[pid]["text"] for pid in ids}
    position = {pid: i for i, pid in enumerate(ids)}
    allowed_cache: dict = {}
    masks, bm25_lists = {}, {}
    for q in questions:
        fkey = json.dumps(q.get("filters") or {}, sort_keys=True)
        if fkey not in allowed_cache:
            allowed = allowed_ids(conn, question_filters(q), ids)
            mask = np.zeros(len(ids), dtype=bool)
            mask[[position[p] for p in allowed]] = True
            allowed_cache[fkey] = mask
        masks[q["item_id"]] = allowed_cache[fkey]
        bm25_lists[q["item_id"]] = bm25_ranking(conn, q["question"], question_filters(q), FUSION_DEPTH, within=ids,
                                                drop_stopwords=drop_stopwords)
    rank_path = coll_dir / "rankings.json"
    build_path = coll_dir / "build.json"
    previous = json.loads(rank_path.read_text(encoding="utf-8")) if rank_path.exists() else {}
    previous_build = json.loads(build_path.read_text(encoding="utf-8")) if build_path.exists() else {}
    same = (previous.get("subcorpus_sha256") == sub["sha256"]
            and previous.get("questions") == [q["item_id"] for q in questions])
    systems = dict(previous.get("systems") or {}) if same else {}
    cand_info = dict(previous_build.get("candidates") or {}) if same else {}
    systems["bm25"] = {qid: lst[:DENSE_TOP] for qid, lst in bm25_lists.items()}
    for cand in candidates:
        info = cand.describe()
        if cand.blocked:
            info.update(status="BLOCKED", reason=cand.blocked)
            cand_info[cand.name] = info
            log(f"[{collection}] {cand.name}: BLOCKED ({cand.blocked})")
            continue
        if cand.paid and skip_paid:
            info.update(status="SKIPPED", reason="paid candidate skipped (--skip-paid)")
            cand_info[cand.name] = info
            log(f"[{collection}] {cand.name}: skipped (--skip-paid)")
            continue
        try:
            encoder = cand.make()
            if hasattr(encoder, "truncation"):
                info["tokenizer_truncation"] = encoder.truncation()
            matrix, owners, emb_stats = passage_matrix(cand, encoder, sub, texts_by_id, emb_dir)
            qmat, q_stats = query_matrix(cand, encoder, questions, emb_dir, sub["sha256"])
        except BudgetExceeded as exc:
            info.update(status="STOPPED", reason=f"stopped by the budget: {exc}")
            cand_info[cand.name] = info
            log(f"[{collection}] {cand.name}: {info['reason']}")
            continue
        if hasattr(encoder, "usd"):
            info["workers_ai"] = {"calls_this_run": encoder.calls, "usd_this_run": round(encoder.usd, 6)}
        info.update(status="BUILT", embedding=emb_stats, query_embedding=q_stats, dim=emb_stats["dim"])
        dense, hybrid = {}, {}
        for n, q in enumerate(questions):
            qid = q["item_id"]
            ranked = dense_ranking(matrix, owners, qmat[n], ids, masks[qid], FUSION_DEPTH)
            dense[qid] = ranked[:DENSE_TOP]
            hybrid[qid] = fuse([bm25_lists[qid], ranked], rrf_k, HYBRID_TOP)
        systems[f"dense {cand.name}"] = dense
        systems[f"hybrid {cand.name}"] = hybrid
        cand_info[cand.name] = info
        log(f"[{collection}] {cand.name}: {emb_stats} query {q_stats['latency']}")
    items = pool_items(collection, questions, systems, rows)
    write_jsonl(coll_dir / "pool_items.jsonl", items)
    _write_json(rank_path, {"format": 1, "collection": collection, "subcorpus_sha256": sub["sha256"],
                            "questions": [q["item_id"] for q in questions], "systems": systems})
    summary = {"format": 1, "collection": collection, "built": now_iso(), "subcorpus_sha256": sub["sha256"],
               "subcorpus_counts": sub["counts"], "corpus_rows": sub["corpus_rows"], "questions": len(questions),
               "rrf_k": rrf_k, "fusion_depth": FUSION_DEPTH, "dense_top": DENSE_TOP, "hybrid_top": HYBRID_TOP,
               "pool_items": len(items), "candidates": cand_info,
               "corpus_pages": corpus_pages(conn),
               "subcorpus_mean_chars": round(sum(len(t or "") for t in texts_by_id.values()) / max(len(ids), 1), 1),
               "subcorpus_mean_chars_cut": round(sum(min(len(t or ""), WORKERS_AI_CHARS) for t in texts_by_id.values())
                                                 / max(len(ids), 1), 1)}
    _write_json(build_path, summary)
    log(f"[{collection}] pool: {len(items)} items over {len(questions)} questions")
    return summary


# --- compact storage ---------------------------------------------------------------------------------

def int8_rows(unit: np.ndarray) -> tuple:
    """Symmetric per-dimension int8 quantization of unit rows: (codes, scale); a row is restored as
    codes * scale / 127. One byte per dimension instead of four."""
    scale = np.abs(unit).max(axis=0).astype(np.float32)
    scale[scale == 0] = 1.0
    codes = np.clip(np.round(unit / scale * 127.0), -127, 127).astype(np.int8)
    return codes, scale


def int8_scores(codes: np.ndarray, scale: np.ndarray, qvec: np.ndarray) -> np.ndarray:
    return codes.astype(np.float32) @ (np.asarray(qvec, dtype=np.float32) * scale / 127.0)


def sign_bits(unit: np.ndarray) -> np.ndarray:
    """One bit per dimension (the sign), packed: dim / 8 bytes per row."""
    return np.packbits(unit > 0, axis=1)


_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def hamming_scores(bits: np.ndarray, qvec: np.ndarray) -> np.ndarray:
    """Negative Hamming distance between each row's sign bits and the query's (higher is closer)."""
    qbits = np.packbits(np.asarray(qvec) > 0)
    return -_POPCOUNT[np.bitwise_xor(bits, qbits)].sum(axis=1).astype(np.float32)


def ranked_from_scores(row_scores: np.ndarray, owners: np.ndarray, ids: list, allowed_mask: np.ndarray, k: int) -> list:
    scores = np.full(len(ids), -np.inf, dtype=np.float32)
    np.maximum.at(scores, owners, row_scores)
    scores[~allowed_mask] = -np.inf
    order = ra.top_k_desc(scores, min(k, int(allowed_mask.sum())))
    return [ids[i] for i in order]


def binary_rescore(bits: np.ndarray, codes: np.ndarray, scale: np.ndarray, owners: np.ndarray, qvec: np.ndarray,
                   ids: list, allowed_mask: np.ndarray, k: int, shortlist: int = BINARY_SHORTLIST) -> list:
    """Sign bits pick a shortlist of rows by Hamming distance; int8 cosine reranks it."""
    row_allowed = allowed_mask[owners]
    ham = hamming_scores(bits, qvec)
    ham[~row_allowed] = -np.inf
    rows = ra.top_k_desc(ham, min(shortlist, int(row_allowed.sum())))
    exact = np.full(len(owners), -np.inf, dtype=np.float32)
    if len(rows):
        exact[rows] = int8_scores(codes[rows], scale, qvec)
    return ranked_from_scores(exact, owners, ids, allowed_mask, k)


def overlap_at(a: list, b: list, k: int = HYBRID_TOP) -> float:
    return len(set(a[:k]) & set(b[:k])) / k if a and b else 0.0


def quantize_collection(conn, collection: str, items_by_id: dict, out_dir: Path, *, rrf_k: int,
                        drop_stopwords: bool) -> dict:
    """Adds int8 and binary-then-int8 systems for every built candidate to rankings.json, from the
    cached embeddings (nothing is embedded again), rebuilds the pool so their new passages get
    judged, and writes quantize.json with how far each compact ranking moved from float32."""
    coll_dir = Path(out_dir) / collection
    emb_dir = coll_dir / "embeddings"
    rankings = json.loads((coll_dir / "rankings.json").read_text(encoding="utf-8"))
    build = json.loads((coll_dir / "build.json").read_text(encoding="utf-8"))
    sub = json.loads((coll_dir / "subcorpus.json").read_text(encoding="utf-8"))
    ids, sha = sub["passage_ids"], sub["sha256"]
    position = {pid: i for i, pid in enumerate(ids)}
    questions = [items_by_id[q] for q in rankings["questions"]]
    masks, bm25 = {}, {}
    for q in questions:
        allowed = allowed_ids(conn, question_filters(q), ids)
        mask = np.zeros(len(ids), dtype=bool)
        mask[[position[pid] for pid in allowed]] = True
        masks[q["item_id"]] = mask
        bm25[q["item_id"]] = bm25_ranking(conn, q["question"], question_filters(q), FUSION_DEPTH, within=ids,
                                          drop_stopwords=drop_stopwords)
    systems = rankings["systems"]
    report = {"format": 1, "collection": collection, "binary_shortlist": BINARY_SHORTLIST, "candidates": {}}
    for name, info in sorted(build["candidates"].items()):
        if info.get("status") != "BUILT":
            continue
        base = emb_dir / f"{name}-{sha[:16]}"
        unit = unit_rows(np.load(base.with_name(base.name + ".npy"), allow_pickle=False))
        row_ids = json.loads(base.with_name(base.name + ".ids.json").read_text(encoding="utf-8"))["row_passage_ids"]
        owners = np.asarray([position[pid] for pid in row_ids], dtype=np.int64)
        qmat = unit_rows(np.load(base.with_name(base.name + ".queries.npy"), allow_pickle=False))
        codes, scale = int8_rows(unit)
        bits = sign_bits(unit)
        variants = {"int8": {}, "binary-rescore": {}}
        for n, q in enumerate(questions):
            qid = q["item_id"]
            variants["int8"][qid] = ranked_from_scores(int8_scores(codes, scale, qmat[n]), owners, ids, masks[qid],
                                                       FUSION_DEPTH)
            variants["binary-rescore"][qid] = binary_rescore(bits, codes, scale, owners, qmat[n], ids, masks[qid],
                                                             FUSION_DEPTH)
        moved = {}
        for v, dense in variants.items():
            systems[f"dense {name} {v}"] = {qid: lst[:DENSE_TOP] for qid, lst in dense.items()}
            hybrid = {qid: fuse([bm25[qid], lst], rrf_k, HYBRID_TOP) for qid, lst in dense.items()}
            systems[f"hybrid {name} {v}"] = hybrid
            ref = systems.get(f"hybrid {name}") or {}
            overlaps = [overlap_at(hybrid[qid], ref.get(qid, [])) for qid in hybrid]
            moved[v] = round(float(np.mean(overlaps)), 4) if overlaps else None
        report["candidates"][name] = {"hybrid_overlap_at_10_with_float32": moved, "dim": int(unit.shape[1]),
                                      "bytes_per_row": {"float32": int(unit.shape[1]) * 4, "int8": int(unit.shape[1]),
                                                        "binary": int(bits.shape[1])}}
        log(f"[{collection}] {name}: compact rankings, overlap@10 with float32 {moved}")
    rows = passage_rows(conn, ids)
    items = pool_items(collection, questions, systems, rows)
    write_jsonl(coll_dir / "pool_items.jsonl", items)
    rankings["systems"] = systems
    _write_json(coll_dir / "rankings.json", rankings)
    report["pool_items"] = len(items)
    _write_json(coll_dir / "quantize.json", report)
    return report


def run_quantize(args, *, open_corpus: Optional[Callable] = None) -> int:
    items_by_id = {}
    for path in args.questions:
        refuse_test_split(path)
        for item in read_jsonl(path):
            items_by_id[item["item_id"]] = item
    open_corpus = open_corpus or _scope_corpus
    for rank_path in sorted(Path(args.out).glob("*/rankings.json")):
        collection = rank_path.parent.name
        conn, rrf_k, drop_stopwords = open_corpus(collection)
        try:
            quantize_collection(conn, collection, items_by_id, Path(args.out), rrf_k=rrf_k, drop_stopwords=drop_stopwords)
        finally:
            conn.close()
    log(f"assembled: {assemble(Path(args.out))}")
    return 0


# --- reranker ----------------------------------------------------------------------------------------

def rerank_call(question: str, texts: list, *, ledger: Ledger, run_id: str, run_cap: float, post: Callable,
                account: str, headers: dict, model: str = RERANKER) -> tuple:
    """(order of texts best first, seconds, usd) from the Workers AI reranker, metered: the worst case
    is reserved before the call and the reported tokens recorded after it."""
    cut = [(t or "")[:WORKERS_AI_CHARS] or " " for t in texts]
    estimate = prices.estimate_input_tokens(question) * len(cut) + sum(prices.estimate_input_tokens(t) for t in cut)
    reservation = f"{run_id}:{model}:{time.time_ns()}"
    ledger.reserve(run_id, run_cap, "workers-ai", model, reservation, prices.cost(model, estimate, 0))
    try:
        t0 = time.perf_counter()
        reply = post(RERANK_URL.format(account=account, model=model), headers,
                     {"query": question, "contexts": [{"text": t} for t in cut], "top_k": len(cut)})
        seconds = time.perf_counter() - t0
        result = reply.get("result") or {}
        usage = result.get("usage") or {}
        tokens = int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
        what = f"ablation rerank {len(cut)} passages" + ("" if tokens else " (usage not reported: worst case)")
        usd = ledger.spend(run_id, "workers-ai", model, tokens or estimate, 0, what=what)
    finally:
        ledger.release(run_id, reservation)
    ranked = sorted(result.get("response") or [], key=lambda r: -float(r.get("score") or 0.0))
    order = [int(r["id"]) for r in ranked if 0 <= int(r.get("id", -1)) < len(cut)]
    if sorted(order) != list(range(len(cut))):
        raise ValueError(f"{model}: the reply does not rank every passage once")
    return order, seconds, usd


def rerank_collection(conn, collection: str, items_by_id: dict, out_dir: Path, *, systems_to_rerank: list,
                      rrf_k: int, ledger: Ledger, run_id: str, run_cap: float, post: Callable, account: str,
                      headers: dict, depth: int = RERANK_DEPTH) -> dict:
    """For each named hybrid system, the fusion's top `depth` (from the stored BM25 and dense top 50),
    reordered by the reranker, top 10 kept as "<system> rerank". The pool is rebuilt so new passages get
    judged; rerank.json records the per-question latency and spend."""
    coll_dir = Path(out_dir) / collection
    rankings = json.loads((coll_dir / "rankings.json").read_text(encoding="utf-8"))
    systems = rankings["systems"]
    sub = json.loads((coll_dir / "subcorpus.json").read_text(encoding="utf-8"))
    rows = passage_rows(conn, sub["passage_ids"])
    questions = [items_by_id[q] for q in rankings["questions"]]
    report = {"format": 1, "collection": collection, "model": RERANKER, "depth": depth, "systems": {}}
    for name in systems_to_rerank:
        dense_name = name.replace("hybrid ", "dense ", 1)
        if name not in systems or dense_name not in systems:
            continue
        out, seconds, usd = {}, [], 0.0
        for q in questions:
            qid = q["item_id"]
            fused = fuse([systems["bm25"].get(qid, []), systems[dense_name].get(qid, [])], rrf_k, depth)
            if not fused:
                out[qid] = []
                continue
            order, secs, cost = rerank_call(q["question"], [rows[pid]["text"] for pid in fused], ledger=ledger,
                                            run_id=run_id, run_cap=run_cap, post=post, account=account, headers=headers)
            out[qid] = [fused[i] for i in order][:HYBRID_TOP]
            seconds.append(secs)
            usd += cost
        systems[f"{name} rerank"] = out
        report["systems"][name] = {"questions": len(seconds), "latency": ra.latency_summary(seconds),
                                   "usd": round(usd, 6)}
        log(f"[{collection}] {name} rerank: {report['systems'][name]}")
    items = pool_items(collection, questions, systems, rows)
    write_jsonl(coll_dir / "pool_items.jsonl", items)
    rankings["systems"] = systems
    _write_json(coll_dir / "rankings.json", rankings)
    report["pool_items"] = len(items)
    _write_json(coll_dir / "rerank.json", report)
    return report


def run_rerank(args, *, open_corpus: Optional[Callable] = None, post: Optional[Callable] = None,
               account: Optional[str] = None, headers: Optional[dict] = None) -> int:
    items_by_id = {}
    for path in args.questions:
        refuse_test_split(path)
        for item in read_jsonl(path):
            items_by_id[item["item_id"]] = item
    if post is None:
        from archive_debugger.audit import net
        post = net.post_json
    if account is None or headers is None:
        account, token = ra.judges.workers_ai_credentials()
        headers = ra.judges.workers_ai_headers(token, ra._gateway_name())
    ledger = Ledger(Path(args.ledger))
    open_corpus = open_corpus or _scope_corpus
    for rank_path in sorted(Path(args.out).glob("*/rankings.json")):
        collection = rank_path.parent.name
        conn, rrf_k, _drop = open_corpus(collection)
        try:
            rerank_collection(conn, collection, items_by_id, Path(args.out), systems_to_rerank=args.systems,
                              rrf_k=rrf_k, ledger=ledger, run_id=args.run_id, run_cap=args.cap, post=post,
                              account=account, headers=headers)
        except BudgetExceeded as exc:
            log(f"[{collection}] rerank stopped by the budget: {exc}")
            return 2
        finally:
            conn.close()
    log(f"assembled: {assemble(Path(args.out))}")
    return 0


def assemble(out_dir: Path) -> dict:
    """The top-level pool_items.jsonl and rankings.json from every collection directory."""
    out_dir = Path(out_dir)
    items, systems = [], {}
    for rank_path in sorted(out_dir.glob("*/rankings.json")):
        coll_dir = rank_path.parent
        items.extend(read_jsonl(coll_dir / "pool_items.jsonl"))
        for system, by_q in json.loads(rank_path.read_text(encoding="utf-8"))["systems"].items():
            systems.setdefault(system, {}).update(by_q)
    write_jsonl(out_dir / "pool_items.jsonl", items)
    _write_json(out_dir / "rankings.json", systems)
    return {"pool_items": len(items), "systems": sorted(systems)}


# --- scoring ----------------------------------------------------------------------------------------

def load_decisions(run_ids: list, runs_dir: Path = RUNS_DIR) -> dict:
    """{item_id: final relevant verdict or None}; a later run replaces an earlier one."""
    out = {}
    for run in run_ids:
        path = Path(runs_dir) / run / "panel.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"no panel decisions at {path}")
        for d in iter_jsonl(path):
            check = (d.get("checks") or {}).get("relevant")
            if check is None:
                continue
            out[d["item_id"]] = check.get("final")
    return out


def question_scores(ranked: list, judged: dict, k: int = POOL_TOP) -> dict:
    """recall@k and nDCG@k of one ranking against one question's judged pool ({passage_id: final
    verdict or None}; a passage absent from it was never judged), plus the unjudged and person
    shares of the top k. recall and nDCG are None when no pooled passage was judged pass."""
    relevant = {pid for pid, v in judged.items() if v == "pass"}
    gains = {pid: GAIN.get(v, 0) for pid, v in judged.items()}
    top = ranked[:k]
    has_pass = bool(relevant)
    return {"recall@10": metrics.recall_at_k(ranked, relevant, k) if has_pass else None,
            "ndcg@10": metrics.ndcg_at_k(ranked, gains, k) if has_pass else None,
            "unjudged@10": (sum(1 for p in top if p not in judged) / len(top)) if top else None,
            "person@10": (sum(1 for p in top if p in judged and judged[p] is None) / len(top)) if top else None}


def paired_bootstrap(system: list, reference: list, *, resamples: int = BOOTSTRAP, seed: int = 0) -> dict:
    """Mean difference (system - reference) over questions and its 95% percentile interval from
    resamples over questions (the same draws for both, so the pairing is kept)."""
    a, b = np.asarray(system, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    if a.size == 0:
        return {"n": 0, "diff": None, "low": None, "high": None}
    diff = a - b
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, diff.size, size=(resamples, diff.size))
    means = diff[draws].mean(axis=1)
    return {"n": int(diff.size), "diff": round(float(diff.mean()), 4),
            "low": round(float(np.percentile(means, 2.5)), 4), "high": round(float(np.percentile(means, 97.5)), 4)}


def index_sizes(rows: int, dim: Optional[int], windows_per_passage: Optional[float] = None) -> dict:
    if not dim:
        return {}
    stored_rows = int(round(rows * windows_per_passage)) if windows_per_passage else rows
    return {"rows": stored_rows, "rows_estimated_from_subcorpus_windows": bool(windows_per_passage),
            "float32_bytes": stored_rows * dim * 4, "int8_bytes": stored_rows * dim,
            "binary_bytes": stored_rows * ((dim + 7) // 8)}


def score_collection(items: list, systems: dict, decisions: dict, seed: int) -> dict:
    judged_by_q: dict = {}
    for it in items:
        judged = judged_by_q.setdefault(it["qid"], {})
        if it["item_id"] in decisions:
            judged[it["passage"]["passage_id"]] = decisions[it["item_id"]]
    qids = sorted(judged_by_q)
    per_system = {}
    for system, by_q in sorted(systems.items()):
        rows = {qid: question_scores(by_q.get(qid, []), judged_by_q[qid]) for qid in qids}
        per_system[system] = rows
    included = [qid for qid in qids if any(v == "pass" for v in judged_by_q[qid].values())]
    out = {"questions": len(qids), "questions_scored": len(included),
           "questions_without_a_pass": len(qids) - len(included), "systems": {}}
    ref = per_system.get(REFERENCE_SYSTEM)
    for system, rows in per_system.items():
        entry = {}
        for metric in ("recall@10", "ndcg@10"):
            vals = [rows[q][metric] for q in included]
            entry[metric] = round(sum(vals) / len(vals), 4) if vals else None
            if ref is not None and system != REFERENCE_SYSTEM:
                entry[f"{metric} diff vs reference"] = paired_bootstrap(
                    vals, [ref[q][metric] for q in included], seed=seed)
        for metric in ("unjudged@10", "person@10"):
            vals = [rows[q][metric] for q in qids if rows[q][metric] is not None]
            entry[metric] = round(sum(vals) / len(vals), 4) if vals else None
        out["systems"][system] = entry
    out["_per_question"] = per_system
    out["_included"] = included
    return out


def pooled_scores(collections_scored: dict, seed: int) -> dict:
    systems = sorted({s for c in collections_scored.values() for s in c["_per_question"]})
    out = {"questions": sum(c["questions"] for c in collections_scored.values()),
           "questions_scored": sum(c["questions_scored"] for c in collections_scored.values()), "systems": {}}
    for system in systems:
        entry = {}
        for metric in ("recall@10", "ndcg@10"):
            vals, refs = [], []
            for c in collections_scored.values():
                rows, ref = c["_per_question"].get(system), c["_per_question"].get(REFERENCE_SYSTEM)
                for q in c["_included"]:
                    if rows is None:
                        continue
                    vals.append(rows[q][metric])
                    if ref is not None:
                        refs.append(ref[q][metric])
            entry[metric] = round(sum(vals) / len(vals), 4) if vals else None
            if system != REFERENCE_SYSTEM and refs and len(refs) == len(vals):
                entry[f"{metric} diff vs reference"] = paired_bootstrap(vals, refs, seed=seed)
        out["systems"][system] = entry
    return out


def spot_sample(items: list, n: int, seed: int) -> list:
    ordered = sorted(items, key=lambda it: it["item_id"])
    return sorted(random.Random(f"spot:{seed}").sample(ordered, min(n, len(ordered))), key=lambda it: it["item_id"])


def _f(v, digits: int = 4) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _ci(d: Optional[dict]) -> str:
    if not d or d.get("diff") is None:
        return ""
    return f"{d['diff']:+.4f} [{d['low']:+.4f}, {d['high']:+.4f}]"


def corpus_pages(conn) -> int:
    """Pages with at least one passage: the unit the whole-collection estimate scales by."""
    return int(conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT item_id, leaf_index FROM passages)").fetchone()[0])


def ledger_usd(ledger_path: Path, run_id: str, model: str) -> float:
    """Everything spent on one model under one run id (resumed runs included)."""
    return sum(float(e.get("usd") or 0.0) for e in read_jsonl(ledger_path)
               if e.get("kind") == "spend" and e.get("run_id") == run_id and e.get("model") == model)


def whole_collection_cost(candidates: dict, builds: dict, *, run_id: Optional[str], ledger_path: Path,
                          iac_pages: int = IAC_PAGES) -> dict:
    """What embedding everything would cost each candidate, from what the sub-corpus build cost:
    for a Workers AI candidate, the ledger's spend on the run divided by the rows it embedded, times
    the rows; for a local one, its measured embedding seconds per row on this laptop's CPU, times the
    rows. Rows are the current index (both collections) and an estimate for the whole Internet
    Archive Canada collection at the current index's passages per page. Estimates, not quotes."""
    rows_now = sum(b["corpus_rows"] for b in builds.values())
    pages_now = sum(b.get("corpus_pages") or 0 for b in builds.values())
    per_page = rows_now / pages_now if pages_now else None
    rows_iac = int(round(per_page * iac_pages)) if per_page else None
    out = {"rows_current_index": rows_now, "pages_current_index": pages_now,
           "passages_per_page": round(per_page, 3) if per_page else None,
           "iac_pages": iac_pages, "rows_iac_estimate": rows_iac, "run_id": run_id, "candidates": {}}
    for name, row in candidates.items():
        emb = row.get("embedding") or {}
        embedded = sum(int(e.get("rows") or 0) for e in emb.values())
        if not embedded:
            continue
        entry = {"rows_embedded": embedded}
        if row.get("paid"):
            usd = ledger_usd(ledger_path, run_id, row["model"]) if run_id else 0.0
            entry["usd_spent"] = round(usd, 4)
            if usd > 0:
                per_row = usd / embedded
                entry["usd_per_million_rows"] = round(per_row * 1e6, 2)
                entry["usd_current_index"] = round(per_row * rows_now, 2)
                entry["usd_iac_estimate"] = round(per_row * rows_iac, 2) if rows_iac else None
        else:
            seconds = sum(float(e.get("embed_seconds") or 0.0) for e in emb.values())
            if seconds > 0:
                per_row = seconds / embedded
                entry["cpu_ms_per_row"] = round(per_row * 1000, 3)
                entry["cpu_hours_current_index"] = round(per_row * rows_now / 3600, 1)
                entry["cpu_hours_iac_estimate"] = round(per_row * rows_iac / 3600, 1) if rows_iac else None
        out["candidates"][name] = entry
    return out


def page_key(passage_id: str) -> str:
    """item#leaf from item#leaf:chunk: the page a passage is on."""
    return passage_id.rsplit(":", 1)[0]


def source_recall(systems: dict, items_by_id: dict, question_ids: list, seed: int, k: int = HYBRID_TOP) -> dict:
    """Per system, the share of questions whose source page is among its first k passages (the
    benchmark runner's recall@10, judged by no one), with Wilson 95% and a paired bootstrap difference
    from the reference system. Questions without a source passage are left out."""
    qids = [q for q in question_ids if source_ids(items_by_id.get(q) or {})]
    hits = {}
    for name, ranked in systems.items():
        row = []
        for q in qids:
            pages = {page_key(pid) for pid in source_ids(items_by_id[q])}
            row.append(1.0 if pages & {page_key(pid) for pid in (ranked.get(q) or [])[:k]} else 0.0)
        hits[name] = row
    ref = hits.get(REFERENCE_SYSTEM)
    out = {}
    for name, row in hits.items():
        n, found = len(row), int(sum(row))
        low, high = calibration.wilson(found, n) if n else (None, None)
        out[name] = {"questions": n, "found": found, "rate": round(found / n, 4) if n else None,
                     "wilson95": [round(low, 4), round(high, 4)] if n else None,
                     "vs_reference": paired_bootstrap(row, ref, seed=seed) if ref is not None and name != REFERENCE_SYSTEM
                     else None}
    return out


def score(out_dir: Path, runs: list, *, runs_dir: Path = RUNS_DIR, seed: int = 0, spot: int = 0,
          build_run_id: Optional[str] = None, ledger_path: Path = LEDGER_PATH,
          questions: Optional[list] = None) -> dict:
    out_dir = Path(out_dir)
    items_by_id = {}
    for path in questions or DEFAULT_QUESTIONS:
        refuse_test_split(path)
        if Path(path).exists():
            for item in read_jsonl(path):
                items_by_id[item["item_id"]] = item
    decisions = load_decisions(runs, runs_dir)
    result = {"format": 1, "generated": now_iso(), "runs": runs, "reference_system": REFERENCE_SYSTEM,
              "bootstrap": {"resamples": BOOTSTRAP, "seed": seed}, "collections": {}, "candidates": {}}
    scored = {}
    builds = {}
    all_items = []
    all_question_ids, all_systems = [], []
    for rank_path in sorted(out_dir.glob("*/rankings.json")):
        coll_dir = rank_path.parent
        collection = coll_dir.name
        items = read_jsonl(coll_dir / "pool_items.jsonl")
        all_items.extend(items)
        systems = json.loads(rank_path.read_text(encoding="utf-8"))["systems"]
        scored[collection] = score_collection(items, systems, decisions, seed)
        result["collections"][collection] = {k: v for k, v in scored[collection].items() if not k.startswith("_")}
        question_ids = json.loads(rank_path.read_text(encoding="utf-8")).get("questions") or []
        result["collections"][collection]["source_recall_at_10"] = source_recall(systems, items_by_id, question_ids, seed)
        all_question_ids.extend(question_ids)
        all_systems.append(systems)
        build_path = coll_dir / "build.json"
        if build_path.exists():
            build = json.loads(build_path.read_text(encoding="utf-8"))
            builds[collection] = build
            for name, info in build.get("candidates", {}).items():
                row = result["candidates"].setdefault(name, {k: info.get(k) for k in (
                    "model", "licence", "runs_on", "paid", "query_prefix_note", "input_note")})
                row.setdefault("status", {})[collection] = info.get("status")
                if info.get("reason"):
                    row.setdefault("reason", {})[collection] = info["reason"]
                emb = info.get("embedding") or {}
                row.setdefault("index_size_whole_collection", {})[collection] = index_sizes(
                    build["corpus_rows"], info.get("dim"), emb.get("windows_per_passage") if info.get("chunked") else None)
                if info.get("query_embedding"):
                    row.setdefault("query_latency", {})[collection] = info["query_embedding"].get("latency")
                if emb:
                    row.setdefault("embedding", {})[collection] = emb
    result["pooled"] = pooled_scores(scored, seed) if scored else {}
    if all_systems:
        names = set.intersection(*(set(sy) for sy in all_systems))
        merged = {n: {q: r for sy in all_systems for q, r in sy[n].items()} for n in names}
        result["source_recall_at_10_pooled"] = source_recall(merged, items_by_id, all_question_ids, seed)
    if builds:
        result["whole_collection_cost"] = whole_collection_cost(result["candidates"], builds, run_id=build_run_id,
                                                                ledger_path=ledger_path)
    result["judged_items"] = sum(1 for it in all_items if it["item_id"] in decisions)
    result["pool_items"] = len(all_items)
    if spot:
        sample = spot_sample(all_items, spot, seed)
        write_jsonl(out_dir / "spot_items.jsonl", sample)
        result["spot"] = {"items": len(sample), "seed": seed, "file": "spot_items.jsonl"}
    _write_json(out_dir / "scores.json", result)
    (out_dir / "scores.md").write_text(scores_markdown(result), encoding="utf-8", newline=NEWLINE)
    return result


def scores_markdown(result: dict) -> str:
    lines = ["# Embedder ablation scores", "",
             f"Generated {result['generated']} by scripts/v2/embedder_ablation.py from audit runs "
             f"{', '.join(result['runs'])}. {result['judged_items']} of {result['pool_items']} pool items judged.", "",
             "Relevant means the panel's final verdict was pass. recall@10 divides by the pooled passages judged",
             "pass for that question; questions with none are left out. nDCG@10 uses gain 2 for pass, 1 for",
             "partial. unjudged@10 and person@10 are the shares of each top 10 with no panel decision or sent",
             f"to a person. Differences are against {result['reference_system']}, mean over questions with a paired",
             f"bootstrap 95% interval ({result['bootstrap']['resamples']} resamples, seed {result['bootstrap']['seed']}).",
             "These are AI-judged labels; read them with the panel's current calibration.", ""]
    sections = list(result["collections"].items()) + ([("pooled", result["pooled"])] if result.get("pooled") else [])
    for name, c in sections:
        lines += [f"## {name}", "", f"Questions: {c['questions']}, scored: {c['questions_scored']}.", "",
                  "| system | recall@10 | diff [95% CI] | nDCG@10 | diff [95% CI] | unjudged@10 | person@10 |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for system, e in c["systems"].items():
            lines.append(f"| {system} | {_f(e.get('recall@10'))} | {_ci(e.get('recall@10 diff vs reference'))} | "
                         f"{_f(e.get('ndcg@10'))} | {_ci(e.get('ndcg@10 diff vs reference'))} | "
                         f"{_f(e.get('unjudged@10'))} | {_f(e.get('person@10'))} |")
        lines.append("")
    lines += ["## Candidates", "",
              "| candidate | model | licence | runs on | status | float32 / int8 / binary index, whole collection |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name, c in result["candidates"].items():
        sizes = "; ".join(f"{coll}: {s['float32_bytes'] / 1e6:,.0f} / {s['int8_bytes'] / 1e6:,.0f} / "
                          f"{s['binary_bytes'] / 1e6:,.0f} MB" + (" (rows estimated)" if s.get(
                              "rows_estimated_from_subcorpus_windows") else "")
                          for coll, s in (c.get("index_size_whole_collection") or {}).items() if s)
        status = ", ".join(f"{k}: {v}" for k, v in (c.get("status") or {}).items())
        lines.append(f"| {name} | {c.get('model')} | {c.get('licence')} | {c.get('runs_on')} | {status} | {sizes} |")
    sr = result.get("source_recall_at_10_pooled")
    if sr:
        lines += ["", "## Source page in the first ten (both collections, judged by no one)", "",
                  "The benchmark runner's recall@10: the share of questions whose source page is among a system's "
                  f"first ten passages, with Wilson 95%; the difference from {result['reference_system']} has a "
                  "paired bootstrap 95% interval.", "",
                  "| System | Found | Rate [Wilson 95%] | Minus reference [95%] |", "| --- | --- | --- | --- |"]
        for name, r in sorted(sr.items(), key=lambda kv: -(kv[1]["rate"] or 0)):
            vs = r.get("vs_reference")
            diff = "-" if not vs or vs.get("diff") is None else f"{vs['diff']:+.4f} [{vs['low']:+.4f}, {vs['high']:+.4f}]"
            ci = r["wilson95"] or [None, None]
            lines.append(f"| {name} | {r['found']}/{r['questions']} | {r['rate']} [{ci[0]}, {ci[1]}] | {diff} |")
    cost = result.get("whole_collection_cost")
    if cost:
        lines += ["", "## Embedding everything: estimated cost per candidate", "",
                  f"Current index {cost['rows_current_index']} passages on {cost['pages_current_index']} pages "
                  f"({cost['passages_per_page']} per page); whole collection about {cost['iac_pages']} pages, so about "
                  f"{cost['rows_iac_estimate']} passages at the same density. Workers AI: the build's ledger spend per "
                  "row; local: embedding seconds per row measured on this laptop's CPU (no GPU). Estimates, not quotes.",
                  "", "| Candidate | Rows embedded | Workers AI USD, current index | Workers AI USD, whole collection | "
                  "CPU hours, current index | CPU hours, whole collection |", "| --- | --- | --- | --- | --- | --- |"]
        for name, c in cost["candidates"].items():
            lines.append(f"| {name} | {c['rows_embedded']} | {c.get('usd_current_index', '-')} | "
                         f"{c.get('usd_iac_estimate', '-')} | {c.get('cpu_hours_current_index', '-')} | "
                         f"{c.get('cpu_hours_iac_estimate', '-')} |")
    return NEWLINE.join(lines) + NEWLINE


# --- CLI ----------------------------------------------------------------------------------------------

def run_build(args, *, lock_path: Path = LOCK_PATH, candidates_factory: Optional[Callable] = None,
              open_corpus: Optional[Callable] = None) -> int:
    try:
        with HeavyLock(lock_path):
            return _build(args, candidates_factory=candidates_factory, open_corpus=open_corpus)
    except LockBusy as exc:
        log(f"not started: {exc}")
        return LOCK_BUSY_STATUS


def _scope_corpus(collection: str):
    """(read-only corpus connection, rrf_k, fts_drop_stopwords) for a collection's scope."""
    from archive_debugger import scopes
    from archive_debugger.audit import collections as audit_collections
    from archive_debugger.eval import rundb
    from archive_debugger.retrieve.config import load_retrieve_config
    scope = scopes.resolve_scope(audit_collections.load(collection).scope)
    if not Path(scope.db_path).exists():
        raise FileNotFoundError(f"the corpus database for {collection} is not here: {scope.db_path}")
    cfg = load_retrieve_config(scope.config_path)
    return rundb.open_corpus_read_only(scope.db_path), cfg.rrf_k, cfg.fts_drop_stopwords


def _build(args, *, candidates_factory=None, open_corpus=None) -> int:
    questions = load_questions(args.questions, args.per_collection, args.seed, set(args.collections))
    if candidates_factory is None:
        ledger_path = Path(args.ledger)

        def candidates_factory():
            return default_candidates(ledger_factory=lambda: Ledger(ledger_path), run_id=args.run_id, run_cap=args.cap)
    wanted = set(args.candidates) if args.candidates else None
    candidates = [c for c in candidates_factory() if wanted is None or c.name in wanted]
    if wanted and wanted - {c.name for c in candidates}:
        raise SystemExit(f"unknown candidates: {sorted(wanted - {c.name for c in candidates})}")
    open_corpus = open_corpus or _scope_corpus
    for collection in args.collections:
        qs = questions.get(collection) or []
        if not qs:
            log(f"[{collection}] no questions; skipped")
            continue
        conn, rrf_k, drop_stopwords = open_corpus(collection)
        try:
            build_collection(conn, collection, qs, candidates, out_dir=Path(args.out), bm25_depth=args.bm25_depth,
                             distractors=args.distractors, seed=args.seed, skip_paid=args.skip_paid, rrf_k=rrf_k,
                             drop_stopwords=drop_stopwords)
        finally:
            conn.close()
    log(f"assembled: {assemble(Path(args.out))}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 3 embedder ablation on a shared sub-corpus.")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="questions, sub-corpus, embeddings, systems, pool")
    b.add_argument("--collections", nargs="+", default=["pilot", "microlog"])
    b.add_argument("--candidates", nargs="+", default=None, help="candidate names (default: all)")
    b.add_argument("--questions", nargs="+", type=Path, default=list(DEFAULT_QUESTIONS))
    b.add_argument("--skip-paid", action="store_true", help="no Workers AI calls")
    b.add_argument("--per-collection", type=int, default=None)
    b.add_argument("--bm25-depth", type=int, default=300)
    b.add_argument("--distractors", type=int, default=30000)
    b.add_argument("--seed", type=int, default=20261101)
    b.add_argument("--run-id", default="embedder-ablation-1")
    b.add_argument("--cap", type=float, default=1.00, help="run cap in US dollars for paid embeddings")
    b.add_argument("--ledger", default=str(ra.LEDGER_PATH))
    b.add_argument("--out", default=str(DEFAULT_OUT))
    s = sub.add_parser("score", help="score the systems from audit panel decisions")
    s.add_argument("--runs", nargs="+", required=True)
    s.add_argument("--spot", type=int, default=0, help="also draw this many pool items for the reference judges")
    s.add_argument("--seed", type=int, default=20261101)
    s.add_argument("--runs-dir", default=str(RUNS_DIR))
    s.add_argument("--out", default=str(DEFAULT_OUT))
    s.add_argument("--build-run-id", default=None, help="the build's --run-id, for the Workers AI spend per row")
    qz = sub.add_parser("quantize", help="add int8 and binary systems from the cached embeddings; rebuild the pool")
    qz.add_argument("--questions", nargs="+", type=Path, default=list(DEFAULT_QUESTIONS))
    qz.add_argument("--out", default=str(DEFAULT_OUT))
    rr = sub.add_parser("rerank", help="rerank hybrid systems' fused top 30 with the Workers AI reranker; rebuild the pool")
    rr.add_argument("--systems", nargs="+", required=True, help='e.g. "hybrid minilm-128" "hybrid bge-m3"')
    rr.add_argument("--questions", nargs="+", type=Path, default=list(DEFAULT_QUESTIONS))
    rr.add_argument("--out", default=str(DEFAULT_OUT))
    rr.add_argument("--run-id", required=True)
    rr.add_argument("--cap", type=float, required=True)
    rr.add_argument("--ledger", default=str(LEDGER_PATH))
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "build":
        for path in args.questions:
            refuse_test_split(path)
        from archive_debugger.local_env import load_local_env
        load_local_env(log=lambda m: None)
        return run_build(args)
    if args.command == "quantize":
        from archive_debugger.local_env import load_local_env
        load_local_env(log=lambda m: None)
        return run_quantize(args)
    if args.command == "rerank":
        from archive_debugger.local_env import load_local_env
        load_local_env(log=lambda m: None)
        return run_rerank(args)
    result = score(Path(args.out), args.runs, runs_dir=Path(args.runs_dir), seed=args.seed, spot=args.spot,
                   build_run_id=args.build_run_id)
    log(f"scored {result['judged_items']} judged of {result['pool_items']} pool items; {Path(args.out) / 'scores.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
