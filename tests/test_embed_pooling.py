"""The dense model keeps fastembed 0.4.2's pooling after the move to fastembed 0.9: the indexes were
built with CLS pooling and L2 normalisation, and fastembed 0.5 and later switched this model to mean
pooling. A stand-in fastembed module records what the helper registers, so no model is downloaded."""
from __future__ import annotations

import sys
import types
from enum import Enum

import pytest

from archive_debugger.retrieve import embed

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class PoolingType(str, Enum):
    CLS = "CLS"
    MEAN = "MEAN"


class ModelSource:
    def __init__(self, hf: str):
        self.hf = hf


class FakeTextEmbedding:
    registered: list = []
    opened: list = []

    def __init__(self, model_name: str):
        FakeTextEmbedding.opened.append(model_name)

    @classmethod
    def list_supported_models(cls):
        return [{"model": MODEL}] + [{"model": r["model"]} for r in cls.registered]

    @classmethod
    def add_custom_model(cls, **kwargs):
        if any(r["model"] == kwargs["model"] for r in cls.registered):
            raise ValueError("already registered")
        cls.registered.append(kwargs)


@pytest.fixture
def fake_fastembed(monkeypatch):
    FakeTextEmbedding.registered = []
    FakeTextEmbedding.opened = []
    root = types.ModuleType("fastembed")
    root.TextEmbedding = FakeTextEmbedding
    common = types.ModuleType("fastembed.common")
    description = types.ModuleType("fastembed.common.model_description")
    description.ModelSource = ModelSource
    description.PoolingType = PoolingType
    monkeypatch.setitem(sys.modules, "fastembed", root)
    monkeypatch.setitem(sys.modules, "fastembed.common", common)
    monkeypatch.setitem(sys.modules, "fastembed.common.model_description", description)
    return FakeTextEmbedding


def test_dense_model_is_opened_with_cls_pooling_and_normalisation(fake_fastembed):
    embed.fastembed_text_model(MODEL)
    legacy = embed.LEGACY_CLS_MODELS[MODEL]
    assert len(fake_fastembed.registered) == 1
    reg = fake_fastembed.registered[0]
    assert reg["model"] == legacy["name"]
    assert reg["pooling"] == PoolingType.CLS
    assert reg["normalization"] is True
    assert reg["sources"].hf == "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    assert reg["model_file"] == "model_optimized.onnx"
    assert reg["dim"] == 384
    assert fake_fastembed.opened == [legacy["name"]]


def test_registration_happens_once(fake_fastembed):
    embed.fastembed_text_model(MODEL)
    embed.fastembed_text_model(MODEL)
    assert len(fake_fastembed.registered) == 1
    assert len(fake_fastembed.opened) == 2


def test_other_models_open_unchanged(fake_fastembed):
    embed.fastembed_text_model("BAAI/bge-small-en-v1.5")
    assert fake_fastembed.registered == []
    assert fake_fastembed.opened == ["BAAI/bge-small-en-v1.5"]


def test_engine_and_jobs_share_the_helper(fake_fastembed):
    embedder = embed.FastEmbedEmbedder(MODEL, 384)
    assert fake_fastembed.opened == [embed.LEGACY_CLS_MODELS[MODEL]["name"]]
    assert embedder.dim == 384
    from archive_debugger.jobs import embed as jobs_embed
    jobs_embed._fastembed({"model": MODEL})
    assert fake_fastembed.opened[-1] == embed.LEGACY_CLS_MODELS[MODEL]["name"]
