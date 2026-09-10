"""Retrieval config loader (reads [index] + [retrieve] from pilot.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RetrieveConfig:
    db_path: Path
    index_path: Path
    embedder: str
    embedding_model: str
    embedding_dim: int
    batch_size: int
    candidates: int
    rrf_k: int
    downweights: dict


def load_retrieve_config(config_path: Path, *, embedder_override: Optional[str] = None) -> RetrieveConfig:
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    idx = raw["index"]
    ret = raw.get("retrieve", {})
    return RetrieveConfig(
        db_path=Path(idx["db_path"]),
        index_path=Path(ret.get("index_path", "index/vectors.db")),
        embedder=embedder_override or ret.get("embedder", "fastembed"),
        embedding_model=idx.get("embedding_model", ""),
        embedding_dim=int(idx.get("embedding_dim", 384)),
        batch_size=int(ret.get("batch_size", 256)),
        candidates=int(ret.get("candidates", 200)),
        rrf_k=int(ret.get("rrf_k", 60)),
        downweights={
            "high": float(ret.get("downweight_high", 1.0)),
            "medium": float(ret.get("downweight_medium", 0.9)),
            "low": float(ret.get("downweight_low", 0.75)),
        },
    )
