"""Embedder abstraction, config-driven. CI/tests use the deterministic stub; the
laptop build uses fastembed. fastembed is imported lazily so importing this module
never pulls the model stack or hits the network (N1 hermetic)."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@runtime_checkable
class Embedder(Protocol):
    dim: int
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class StubEmbedder:
    """Deterministic hashing embedder: L2-normalized bag of hashed tokens. No
    model, no network. Cosine similarity tracks token overlap, so fixture tests
    are meaningful and stable."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in _tokens(text):
            h = int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v] if norm else v

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


# fastembed 0.4.2 ran this model's ONNX file with CLS pooling and L2 normalisation. fastembed 0.5
# and later run the same file with mean pooling, which gives different vectors (measured 2026-11-11
# on 300 passages: lowest cosine 0.33, a different top 10 for every test query). Every index here
# was built the 0.4.2 way, so the model is registered under its own name with 0.4.2's pooling; with
# onnxruntime 1.19.2 the vectors are identical to 0.4.2's (largest difference 0 on the same sample).
LEGACY_CLS_MODELS = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {
        "name": "archive-argues/paraphrase-multilingual-MiniLM-L12-v2-cls-normalized",
        "hf": "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q",
        "model_file": "model_optimized.onnx",
        "dim": 384,
    },
}


def fastembed_text_model(model_id: str):
    """A fastembed TextEmbedding for `model_id` that gives the vectors the project's indexes hold."""
    from fastembed import TextEmbedding  # noqa: imported lazily on purpose
    legacy = LEGACY_CLS_MODELS.get(model_id)
    if legacy is None:
        return TextEmbedding(model_name=model_id)
    from fastembed.common.model_description import ModelSource, PoolingType
    known = {m["model"] for m in TextEmbedding.list_supported_models()}
    if legacy["name"] not in known:
        TextEmbedding.add_custom_model(
            model=legacy["name"], pooling=PoolingType.CLS, normalization=True,
            sources=ModelSource(hf=legacy["hf"]), dim=legacy["dim"], model_file=legacy["model_file"],
        )
    return TextEmbedding(model_name=legacy["name"])


class FastEmbedEmbedder:
    """Real embedder. Lazy fastembed import keeps CI hermetic."""

    def __init__(self, model_id: str, dim: int):
        self.model_id = model_id
        self.dim = dim
        self._model = fastembed_text_model(model_id)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        fn = getattr(self._model, "query_embed", None) or self._model.embed
        return list(map(float, next(iter(fn([text])))))


def make_embedder(kind: str, model_id: str, dim: int) -> Embedder:
    if kind == "stub":
        return StubEmbedder(dim=dim)
    if kind == "fastembed":
        return FastEmbedEmbedder(model_id=model_id, dim=dim)
    raise ValueError(f"unknown embedder kind: {kind}")
