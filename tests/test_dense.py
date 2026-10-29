"""Resident dense index (retrieve/dense.py): in-place normalization is bit-identical to the old
formula and holds one copy of the matrix, the memory guard budgets what a load really adds, and the
server's pooled retrievers share one resident index per scope. Hermetic: fixture databases, stub
embedder, no network."""
from __future__ import annotations

import importlib.util
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from archive_debugger.retrieve import dense

REPO = Path(__file__).resolve().parents[1]


def _old_normalize(mat: np.ndarray) -> np.ndarray:
    """The pre-v2 normalization, kept here only as the reference the fix must match bit for bit."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32, copy=False)


@pytest.mark.parametrize("n,dim,seed", [(1, 384, 0), (7, 3, 1), (16384, 384, 2), (40001, 384, 3), (5000, 64, 4)])
def test_normalize_rows_is_byte_identical(n, dim, seed):
    rng = np.random.default_rng(seed)
    mat = rng.standard_normal((n, dim)).astype(np.float32)
    mat[:: max(1, n // 5)] *= np.float32(1e-3)        # mixed magnitudes
    if n > 3:
        mat[2] = 0.0                                     # a zero row stays zero
    expected = _old_normalize(mat.copy())
    got = dense.normalize_rows(mat)
    assert got is mat                                    # in place
    assert got.dtype == np.float32
    assert np.array_equal(got, expected)
    assert got.tobytes() == expected.tobytes()


def test_normalize_rows_holds_one_copy():
    mat = np.random.default_rng(5).standard_normal((50000, 384)).astype(np.float32)   # ~77 MB
    reference = mat.copy()
    tracemalloc.start()
    _old_normalize(reference)
    _, old_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tracemalloc.start()
    dense.normalize_rows(mat)
    _, new_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert old_peak >= mat.nbytes                        # the old formula allocated a second full matrix
    assert new_peak < 0.5 * mat.nbytes / 1.5             # the fix adds only the norms and one row block


def _fixture_dbs(tmp_path) -> Path:
    spec = importlib.util.spec_from_file_location("make_fixture_db", REPO / "scripts" / "make_fixture_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main([str(tmp_path / "data")]) == 0
    return tmp_path / "data"


def test_guard_counts_ids_and_norms(tmp_path, monkeypatch):
    """A load whose matrix alone fits under the safe fraction but whose ids, dict and norms do not is
    refused, so the guard no longer under-budgets by the Python-side cost."""
    import sqlite3
    import sqlite_vec
    data = _fixture_dbs(tmp_path)
    conn = sqlite3.connect(f"file:{data / 'civic.db'}?mode=ro", uri=True)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("ATTACH DATABASE ? AS vec", (f"file:{data / 'vectors.db'}?mode=ro",))
    n = conn.execute("SELECT COUNT(*) FROM vec.passages_vec").fetchone()[0]
    dim = np.frombuffer(conn.execute("SELECT embedding FROM vec.passages_vec LIMIT 1").fetchone()[0],
                        dtype=np.float32).shape[0]
    matrix_only = n * dim * 4
    full = dense.resident_bytes(n, dim)
    assert full > matrix_only
    rss = 1000
    limit = int((rss + (matrix_only + full) / 2) / dense._SAFE_FRACTION)   # between the two budgets
    monkeypatch.setenv(dense.ENV_BACKEND, "numpy")
    monkeypatch.setattr(dense, "_container_limit", lambda: limit)
    monkeypatch.setattr(dense, "_rss", lambda: rss)
    logs: list[str] = []
    assert dense.load_if_enabled(conn, log=logs.append) is None
    assert "would not fit" in logs[0]
    monkeypatch.setattr(dense, "_container_limit", lambda: int((rss + full) / dense._SAFE_FRACTION) + 1)
    idx = dense.load_if_enabled(conn, log=logs.append)
    assert idx is not None and idx.n == n
    conn.close()


def test_pool_shares_one_resident_index(tmp_path, monkeypatch):
    data = _fixture_dbs(tmp_path)
    monkeypatch.setenv("CIVIC_DB_PATH", str(data / "civic.db"))
    monkeypatch.setenv("CIVIC_INDEX_PATH", str(data / "vectors.db"))
    monkeypatch.setenv("CIVIC_EMBEDDER", "stub")
    monkeypatch.setenv(dense.ENV_BACKEND, "numpy")
    monkeypatch.setattr(dense, "_container_limit", lambda: None)
    from archive_debugger.api import app as app_module
    from archive_debugger.api.app import POOL_SIZE, create_app
    # The warm thread primes the model client, which imports the SDK; keep this test hermetic.
    monkeypatch.setattr(app_module, "_prime_model_client", lambda: None)
    app = create_app(REPO / "config" / "pilot.toml", provider="stub", load_env=False,
                     web_dist=tmp_path / "nodist", cache_path=tmp_path / "cache" / "answers.db")
    with TestClient(app):
        # Let the boot-warm thread finish before the lifespan closes the connections it is using.
        assert app.state.ready.wait(timeout=120)
        bundle = app.state.bundles["pilot"]
        base = bundle.retriever.dense_index
        assert isinstance(base, dense.DenseIndex)
        pooled = bundle.pool._all
        assert len(pooled) == POOL_SIZE
        assert all(r.dense_index is base for r in pooled)                    # one resident array per scope
        assert all(r.dense_index._m is base._m for r in pooled)
