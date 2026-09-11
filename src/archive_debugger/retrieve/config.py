"""Retrieval config loader (reads [index] + [retrieve] from pilot.toml). The two
data-file paths honor the CIVIC_DB_PATH / CIVIC_INDEX_PATH env overrides, and
CIVIC_EMBEDDER overrides [retrieve].embedder (CI smoke runs set it to "stub" against
a fixture index so no model is downloaded).

Phase 13 switches (all default off = Phase 7 behavior): section_demote,
fts_drop_stopwords, doc_type_family_filter, per_item_cap (0 = off), later_years_flag;
pool_size is the number of hits handed to the evidence trail."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from archive_debugger.ingest.db import ENV_DB_PATH, ENV_INDEX_PATH, env_path

ENV_EMBEDDER = "CIVIC_EMBEDDER"


def default_section_weights() -> dict:
    return {"front": 0.5, "body": 1.0, "back": 0.5}


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
    section_demote: bool = False
    section_weights: dict = field(default_factory=default_section_weights)
    fts_drop_stopwords: bool = False
    doc_type_family_filter: bool = False
    doc_type_families: dict = field(default_factory=dict)
    pool_size: int = 30
    per_item_cap: int = 0
    later_years_flag: bool = False

    def switches(self) -> dict:
        """The Phase 13 switch state, for eval_runs rows and the cache fingerprint."""
        return {
            "section_demote": self.section_demote,
            "section_weights": dict(self.section_weights),
            "fts_drop_stopwords": self.fts_drop_stopwords,
            "doc_type_family_filter": self.doc_type_family_filter,
            "pool_size": self.pool_size,
            "per_item_cap": self.per_item_cap,
            "later_years_flag": self.later_years_flag,
        }

    def active_families(self) -> dict:
        return self.doc_type_families if self.doc_type_family_filter else {}


def load_retrieve_config(config_path: Path, *, embedder_override: Optional[str] = None) -> RetrieveConfig:
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    idx = raw["index"]
    ret = raw.get("retrieve", {})
    return RetrieveConfig(
        db_path=env_path(ENV_DB_PATH, idx["db_path"]),
        index_path=env_path(ENV_INDEX_PATH, ret.get("index_path", "index/vectors.db")),
        embedder=embedder_override or os.environ.get(ENV_EMBEDDER) or ret.get("embedder", "fastembed"),
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
        section_demote=bool(ret.get("section_demote", False)),
        section_weights={
            "front": float(ret.get("section_weight_front", 0.5)),
            "body": 1.0,
            "back": float(ret.get("section_weight_back", 0.5)),
        },
        fts_drop_stopwords=bool(ret.get("fts_drop_stopwords", False)),
        doc_type_family_filter=bool(ret.get("doc_type_family_filter", False)),
        doc_type_families={k: [str(m) for m in v] for k, v in ret.get("doc_type_families", {}).items()},
        pool_size=int(ret.get("pool_size", 30)),
        per_item_cap=int(ret.get("per_item_cap", 0)),
        later_years_flag=bool(ret.get("later_years_flag", False)),
    )
