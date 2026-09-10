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


class FastEmbedEmbedder:
    """Real embedder. Lazy fastembed import keeps CI hermetic."""

    def __init__(self, model_id: str, dim: int):
        from fastembed import TextEmbedding  # noqa: imported lazily on purpose
        self.model_id = model_id
        self.dim = dim
        self._model = TextEmbedding(model_name=model_id)

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
