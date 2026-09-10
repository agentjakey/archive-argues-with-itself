"""Build the dense vector index (laptop job). Reads passage text from civic.db,
embeds in batches, writes vectors into a SEPARATE sqlite artifact using
sqlite-vec float32 serialization. Resumable: passages already indexed are skipped
and each batch is committed. Never re-fetches IA; CI never runs this."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional

import sqlite_vec

from archive_debugger.retrieve.config import load_retrieve_config
from archive_debugger.retrieve.embed import Embedder, make_embedder

VEC_SCHEMA = """
CREATE TABLE IF NOT EXISTS passages_vec (
    passage_id TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT);
"""


def open_vectors(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(VEC_SCHEMA)
    return conn


def _assert_meta(vec: sqlite3.Connection, embedder: Embedder, model_id: str) -> None:
    cur = dict(vec.execute("SELECT key, value FROM index_meta").fetchall())
    if "dim" in cur and cur["dim"] != str(embedder.dim):
        raise ValueError(f"index dim {cur['dim']} != embedder dim {embedder.dim}; refuse to mix")
    if "model" in cur and model_id and cur["model"] != model_id:
        raise ValueError(f"index model {cur['model']} != {model_id}; refuse to mix")
    vec.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES ('dim', ?)", (str(embedder.dim),))
    if model_id:
        vec.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES ('model', ?)", (model_id,))
    vec.commit()


def _flush(vec: sqlite3.Connection, embedder: Embedder, ids: list[str], txt: list[str]) -> int:
    vecs = embedder.embed_passages(txt)
    vec.executemany(
        "INSERT OR REPLACE INTO passages_vec(passage_id, embedding) VALUES (?, ?)",
        [(i, sqlite_vec.serialize_float32(v)) for i, v in zip(ids, vecs)],
    )
    vec.commit()
    return len(ids)


def build_index(civic_path: Path, vectors_path: Path, embedder: Embedder, *,
                model_id: str = "", batch_size: int = 256, limit: Optional[int] = None) -> int:
    civ = sqlite3.connect(f"file:{civic_path}?mode=ro", uri=True)
    Path(vectors_path).parent.mkdir(parents=True, exist_ok=True)
    vec = open_vectors(str(vectors_path))
    try:
        _assert_meta(vec, embedder, model_id)
        done = {r[0] for r in vec.execute("SELECT passage_id FROM passages_vec")}
        ids: list[str] = []
        txt: list[str] = []
        wrote = 0
        for pid, text in civ.execute("SELECT passage_id, text FROM passages ORDER BY passage_id"):
            if pid in done:
                continue
            ids.append(pid)
            txt.append(text or "")
            if len(ids) >= batch_size:
                wrote += _flush(vec, embedder, ids, txt)
                ids, txt = [], []
                if limit and wrote >= limit:
                    break
        if ids and not (limit and wrote >= limit):
            wrote += _flush(vec, embedder, ids, txt)
        count = vec.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0]
        vec.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES ('count', ?)", (str(count),))
        vec.commit()
        return wrote
    finally:
        civ.close()
        vec.close()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Build the dense vector index (laptop job).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--limit", type=int, default=None, help="cap NEW vectors this run (batches)")
    args = p.parse_args(argv)
    cfg = load_retrieve_config(args.config)
    embedder = make_embedder(cfg.embedder, cfg.embedding_model, cfg.embedding_dim)
    wrote = build_index(cfg.db_path, cfg.index_path, embedder,
                        model_id=cfg.embedding_model, batch_size=cfg.batch_size, limit=args.limit)
    conn = sqlite3.connect(str(cfg.index_path))
    total = conn.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0]
    conn.close()
    print(f"indexed {wrote} new; {total} total vectors -> {cfg.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
