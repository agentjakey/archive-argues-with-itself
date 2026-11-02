"""The embed job: passages into dense vectors in the index format named by the job's index spec.

Input unit: <input_prefix>/shards/<id>.jsonl.gz, one {"passage_id", "text"} per line, in order.
Output: <id>.npz holding "matrix" (rows in input order, the spec's dtype, unit length when the spec
normalizes) and "ids" (the passage ids). Backends: fastembed on CPU, sentence-transformers on a GPU,
or a Workers AI embedding model when the job's model exists there (bge-m3, qwen3-embedding)."""
from __future__ import annotations

import gzip
import io
import json
import os
import tomllib
from pathlib import Path
from typing import Callable

import numpy as np

from archive_debugger.audit.budget import Ledger, worst_case
from archive_debugger.jobs import net
from archive_debugger.jobs.spec import REPO, JobSpec, executor_settings

WORKERS_AI_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


def load_index_spec(spec: JobSpec) -> dict:
    path = Path(spec.params.get("index_spec", "config/jobs/index_spec.toml"))
    path = path if path.is_absolute() else REPO / path
    with path.open("rb") as fh:
        return tomllib.load(fh)


def read_shard(raw: bytes) -> tuple:
    rows = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").splitlines() if line.strip()]
    return [r["passage_id"] for r in rows], [r["text"] or "" for r in rows]


def write_shard(rows: list) -> bytes:
    body = "".join(json.dumps({"passage_id": r["passage_id"], "text": r["text"]}, ensure_ascii=False) + "\n" for r in rows)
    return gzip.compress(body.encode("utf-8"), mtime=0)


def _fastembed(index: dict) -> Callable:
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=index["model"])
    return lambda texts: np.array(list(model.embed(texts)), dtype=np.float32)


def _sentence_transformers(index: dict) -> Callable:
    from sentence_transformers import SentenceTransformer
    import torch
    model = SentenceTransformer(index["model"], device="cuda" if torch.cuda.is_available() else "cpu")
    model.max_seq_length = int(index["max_seq_length"])
    return lambda texts: model.encode(texts, batch_size=128, convert_to_numpy=True).astype(np.float32)


def _workers_ai(model: str, post: Callable = None, meter: tuple = None, gateway: str = None,
               batch_texts: int = 100) -> Callable:
    """Workers AI embeddings, metered in the scale ledger: the worst case (every character a token)
    is reserved before each call and the provider's count recorded after. With a gateway (the
    executor's `gateway`, for example archive-argues-audit), each request names it and carries the
    gateway's token, as the audit's judges do; batch text only, never visitor data. `batch_texts` is
    the index spec's texts per call (bge-m3 rejects calls over 60,000 tokens: 50 noisy OCR passages
    crossed it, so the v2 spec says 20)."""
    from archive_debugger.audit.judges import workers_ai_headers
    post = post or net.post_json
    account, token = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_AI_TOKEN")
    if not account or not token:
        raise RuntimeError("the Workers AI executor needs CF_ACCOUNT_ID and CF_AI_TOKEN")
    url = WORKERS_AI_RUN.format(account=account, model=model)
    headers = workers_ai_headers(token, gateway)

    def embed(texts):
        out = []
        for i in range(0, len(texts), batch_texts):
            chunk = texts[i:i + batch_texts]
            reservation = None
            if meter is not None:
                ledger, run_id, run_cap = meter
                reservation = f"{run_id}:embed:{i}:{len(chunk)}:{sum(map(len, chunk))}"
                ledger.reserve(run_id, run_cap, "workers-ai", model, reservation, worst_case(model, sum(map(len, chunk)), 0))
            try:
                reply = post(url, headers, {"text": chunk})
                if meter is not None:
                    tokens = int((reply.get("result") or {}).get("usage", {}).get("prompt_tokens") or sum(map(len, chunk)) // 3)
                    ledger.spend(run_id, "workers-ai", model, tokens, 0, what=f"embed {len(chunk)} passages")
            finally:
                if reservation is not None:
                    ledger.release(run_id, reservation)
            out.extend(reply["result"]["data"])
        return np.array(out, dtype=np.float32)
    return embed


def make_backend(spec: JobSpec, executor: str, index: dict, post: Callable = None) -> tuple:
    settings = executor_settings(spec, executor)
    backend = settings.get("backend") or (index.get("backends") or {}).get(executor)
    if executor == "workers_ai" or backend == "workers_ai":
        # The index spec, when it names a Workers AI model for itself, decides; a job's own setting
        # may only repeat it, so the vectors are always the index's model.
        spec_model = (index.get("index") or {}).get("workers_ai_model")
        model = settings.get("model") or spec_model
        if spec_model and model != spec_model:
            raise RuntimeError(f"the job names {model} but the index spec's Workers AI model is {spec_model}")
        if not model:
            raise RuntimeError("this index's model is not on Workers AI: the index spec names no workers_ai_model")
        if "run_cap_usd" not in settings:
            raise RuntimeError("a paid endpoint needs run_cap_usd in [executor.workers_ai]")
        from archive_debugger.jobs.judge import LEDGER, PHASE_CAP_USD
        # The whole-collection embedding has its own ledger and cap (docs/v2/DECISIONS.md); other
        # embed jobs share the scale ledger.
        ledger_path = REPO / settings["ledger"] if settings.get("ledger") else LEDGER
        phase_cap = float(settings.get("phase_cap_usd", PHASE_CAP_USD))
        meter = (Ledger(ledger_path, phase_cap=phase_cap), f"{spec.name}:{settings.get('run', 'run-1')}",
                 float(settings["run_cap_usd"]))
        batch_texts = int((index.get("index") or {}).get("batch_texts", 100))
        return "workers_ai:" + model, _workers_ai(model, post, meter, settings.get("gateway"), batch_texts)
    if backend == "sentence_transformers":
        return backend, _sentence_transformers(index["index"])
    if backend == "fastembed":
        return backend, _fastembed(index["index"])
    raise RuntimeError(f"unknown embedding backend {backend!r}")


def make_process(spec: JobSpec, executor: str, *, embed_fn: Callable = None, backend_name: str = None) -> Callable:
    index = load_index_spec(spec)
    if embed_fn is None:
        backend_name, embed_fn = make_backend(spec, executor, index)
    idx = index["index"]
    batch = int(spec.params.get("batch", 256))

    def process(unit: dict, store, _spec: JobSpec) -> tuple:
        ids, texts = read_shard(store.get(f"{spec.input_prefix.rstrip('/')}/shards/{unit['id']}.jsonl.gz"))
        # The index spec's max_chars cuts each passage before the prefix is added (the v2 spec: 2,000).
        max_chars = int(idx.get("max_chars") or 0)
        texts = [idx.get("passage_prefix", "") + (t[:max_chars] if max_chars else t) for t in texts]
        parts = [embed_fn(texts[i:i + batch]) for i in range(0, len(texts), batch)]
        matrix = np.vstack(parts) if parts else np.zeros((0, int(idx["dim"])), dtype=np.float32)
        if matrix.shape != (len(ids), int(idx["dim"])):
            raise ValueError(f"embedding shape {matrix.shape} is not ({len(ids)}, {idx['dim']})")
        if idx.get("normalize"):
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix / np.where(norms == 0, 1, norms)
        matrix = matrix.astype(idx.get("dtype", "float32"))
        buf = io.BytesIO()
        np.savez(buf, matrix=matrix, ids=np.array(ids))
        return buf.getvalue(), "npz", {"model": idx["model"], "backend": backend_name, "rows": len(ids),
                                       "index": idx["name"]}
    return process
