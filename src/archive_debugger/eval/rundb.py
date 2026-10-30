"""Where evaluation runs are recorded: a separate SQLite file, never a served data file.

On 2026-10-08 an evaluation report wrote eval_runs and eval_results rows into the serving
civic.db, so that file no longer matched its published sha256. The
evaluation code now reads labels from the corpus database through a read-only connection and
writes its runs here: CIVIC_EVAL_DB, or data/eval/eval_runs.db.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from archive_debugger import scopes

ENV_EVAL_DB = "CIVIC_EVAL_DB"
DEFAULT_EVAL_DB = Path("data/eval/eval_runs.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id      TEXT PRIMARY KEY,
    git_sha     TEXT,
    config_json TEXT,
    ts          TEXT
);
CREATE TABLE IF NOT EXISTS eval_results (
    run_id TEXT NOT NULL REFERENCES eval_runs(run_id),
    qid    TEXT NOT NULL,
    metric TEXT NOT NULL,
    value  REAL,
    PRIMARY KEY (run_id, qid, metric)
);
"""


def eval_db_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    value = os.environ.get(ENV_EVAL_DB)
    return Path(value) if value else DEFAULT_EVAL_DB


def open_eval_db(path: Optional[Path] = None) -> sqlite3.Connection:
    """The evaluation run database, created when missing."""
    target = eval_db_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def open_corpus_read_only(db_path: Path | str) -> sqlite3.Connection:
    """The corpus database for reading labels and questions: read-only, so an evaluation can never
    change a file that is served or published."""
    scopes.guard_path(db_path)
    conn = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
