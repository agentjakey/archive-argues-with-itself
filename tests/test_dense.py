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


def _open_fixture(data: Path):
    import sqlite3
    import sqlite_vec
    conn = sqlite3.connect(f"file:{data / 'civic.db'}?mode=ro", uri=True)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("ATTACH DATABASE ? AS vec", (f"file:{(data / 'vectors.db').as_posix()}?mode=ro",))
    return conn


def test_guard_counts_anonymous_memory_ids_norms_and_headroom(tmp_path, monkeypatch):
    """A load whose matrix alone fits but whose ids, dict, norms and the headroom do not is refused;
    the guard counts anonymous memory, never memory-mapped page cache."""
    data = _fixture_dbs(tmp_path)
    conn = _open_fixture(data)
    n = conn.execute("SELECT COUNT(*) FROM vec.passages_vec").fetchone()[0]
    dim = np.frombuffer(conn.execute("SELECT embedding FROM vec.passages_vec LIMIT 1").fetchone()[0],
                        dtype=np.float32).shape[0]
    matrix_only = n * dim * 4
    full = dense.resident_bytes(n, dim)
    assert full > matrix_only
    anon, headroom = 1000, 4096
    monkeypatch.setenv(dense.ENV_BACKEND, "numpy")
    monkeypatch.setenv(dense.ENV_HEADROOM_MB, "0")
    monkeypatch.setattr(dense, "headroom_bytes", lambda: headroom)
    monkeypatch.setattr(dense, "_anon_bytes", lambda: anon)
    monkeypatch.setattr(dense, "_container_limit", lambda: anon + matrix_only + headroom)
    logs: list[str] = []
    assert dense.load_if_enabled(conn, log=logs.append) is None
    assert "would not fit" in logs[0] and "headroom_mb" in logs[0]
    monkeypatch.setattr(dense, "_container_limit", lambda: anon + full + headroom)
    idx = dense.load_if_enabled(conn, log=logs.append)
    assert idx is not None and idx.n == n
    conn.close()


def test_fits_rule():
    assert dense.fits(10, limit=100, anon=50, headroom=40)
    assert not dense.fits(11, limit=100, anon=50, headroom=40)
    assert dense.fits(10 ** 12, limit=None, anon=50, headroom=40)           # no container limit
    assert dense.fits(10 ** 12, limit=100, anon=None, headroom=40)          # no /proc (not Linux)


def test_artifacts_are_byte_identical_and_preferred(tmp_path, monkeypatch):
    """The .npy artifacts hold exactly the matrix and ids the row-by-row load builds, and the loader
    uses them when they describe the attached index."""
    data = _fixture_dbs(tmp_path)
    conn = _open_fixture(data)
    want_mat, want_ids = dense.read_rows(conn)
    manifest = dense.build_artifacts(conn, data / "vectors.db", log=lambda _m: None)
    assert manifest["rows"] == want_mat.shape[0] and manifest["index_sha256"] == dense.file_sha256(data / "vectors.db")
    got_mat, got_ids = dense.load_artifacts(data / "vectors.db", manifest)
    assert np.array_equal(got_mat, want_mat) and got_mat.tobytes() == want_mat.tobytes()
    assert got_ids == want_ids
    monkeypatch.setenv(dense.ENV_BACKEND, "numpy")
    monkeypatch.setattr(dense, "_container_limit", lambda: None)
    logs: list[str] = []
    idx = dense.load_if_enabled(conn, log=logs.append)
    assert idx is not None and "from artifacts" in logs[-1]
    assert idx._m.tobytes() == want_mat.tobytes() and idx._ids == want_ids
    conn.close()


def test_artifacts_for_another_index_are_ignored(tmp_path, monkeypatch):
    import json
    data = _fixture_dbs(tmp_path)
    conn = _open_fixture(data)
    dense.build_artifacts(conn, data / "vectors.db", log=lambda _m: None)
    manifest_path = dense.artifact_paths(data / "vectors.db")["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["index_bytes"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert dense.usable_artifacts(data / "vectors.db") is None
    monkeypatch.setenv(dense.ENV_BACKEND, "numpy")
    monkeypatch.setattr(dense, "_container_limit", lambda: None)
    logs: list[str] = []
    assert dense.load_if_enabled(conn, log=logs.append) is not None and "from sqlite rows" in logs[-1]
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
