"""Resident in-memory dense retrieval (A4), behind CIVIC_DENSE_BACKEND=numpy (default sqlite).

The default dense leg is a per-row vec_distance_cosine scan over the whole sqlite-vec index, which is
slow on a shared vCPU and, when the index is not held resident, re-reads it on every query. This
module holds one scope's vectors resident as a normalized float32 matrix and does the dense leg as a
single vectorized exact cosine (one matvec + argpartition top-k). It is exact, not approximate: the
rows are L2-normalized once at load and the query at search time, both in float32, so the returned
candidate SET matches the sqlite-vec scan; only tie order at identical distances may differ.

Boundaries: read-only, local-file only (loads from the already-open vec.passages_vec, no network, N1).
Generation, the prompt, the abstention rule, BM25, RRF fusion, top_k, and the passage-id mapping are
all unchanged; only the dense candidate leg is replaced. Enabling the flag can never OOM or break
serving: the load is guarded by the container memory limit and any failure falls back to sqlite-vec.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

ENV_BACKEND = "CIVIC_DENSE_BACKEND"   # "sqlite" (default) | "numpy"
_SAFE_FRACTION = 0.90                 # refuse a resident load that would exceed this share of the limit

Log = Callable[[str], None]


def backend_is_numpy() -> bool:
    return os.environ.get(ENV_BACKEND, "sqlite").strip().lower() == "numpy"


class DenseIndex:
    """One scope's resident, L2-normalized vectors plus the exact vectorized cosine dense leg."""

    def __init__(self, matrix: np.ndarray, ids: list):
        self._m = matrix                                   # (n, dim) float32, rows L2-normalized
        self._ids = ids                                    # row index -> passage_id
        self._row = {pid: i for i, pid in enumerate(ids)}  # passage_id -> row index
        self.n, self.dim = matrix.shape

    def _topk(self, sims: np.ndarray, k: int) -> np.ndarray:
        if k >= sims.shape[0]:
            return np.argsort(-sims)
        part = np.argpartition(-sims, k)[:k]
        return part[np.argsort(-sims[part])]

    def search(self, qvec, allowed_ids: Optional[list], k: int) -> list:
        """Top-k passage ids by exact cosine. allowed_ids=None scans every vector (no filter); a list
        restricts to those passages first (the same filter semantics as the sqlite-vec WHERE), then
        ranks, matching 'filter then order then limit'."""
        q = np.asarray(qvec, dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm:
            q = q / norm
        if allowed_ids is None:
            sims = self._m @ q
            order = self._topk(sims, k)
            return [self._ids[i] for i in order]
        rows = np.fromiter((self._row[p] for p in allowed_ids if p in self._row), dtype=np.int64)
        if rows.size == 0:
            return []
        sims = self._m[rows] @ q
        order = self._topk(sims, min(k, rows.size))
        return [self._ids[rows[i]] for i in order]


def _container_limit() -> Optional[int]:
    """The container memory limit in bytes from the cgroup (v2 then v1), or None when unreadable or
    unset ('max'/sentinel). No external call."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw and raw != "max":
            try:
                val = int(raw)
            except ValueError:
                return None
            return None if val > (1 << 50) else val
    return None


def _rss() -> Optional[int]:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def load_if_enabled(conn, *, log: Log = print) -> Optional[DenseIndex]:
    """Build a resident DenseIndex from conn's attached vec.passages_vec when CIVIC_DENSE_BACKEND=numpy
    and it fits under the container memory limit; otherwise None, so the caller keeps the sqlite-vec
    leg. Never raises: any failure logs and returns None, so enabling the flag can never OOM the box
    or break serving (degrade, never error). conn must have the vec database attached (the Retriever's
    own connection)."""
    if not backend_is_numpy():
        return None
    try:
        n = conn.execute("SELECT COUNT(*) FROM vec.passages_vec").fetchone()[0]
        if n == 0:
            return None
        first = conn.execute("SELECT embedding FROM vec.passages_vec LIMIT 1").fetchone()
        dim = int(np.frombuffer(first[0], dtype=np.float32).shape[0])
        est = n * dim * 4   # float32 bytes
        limit, rss = _container_limit(), _rss()
        if limit is not None and rss is not None and (rss + est) > _SAFE_FRACTION * limit:
            log(f"[dense] would not fit: est_mb={est / 1e6:.0f} rss_mb={rss / 1e6:.0f} "
                f"limit_mb={limit / 1e6:.0f} (>{_SAFE_FRACTION:.0%}); keeping sqlite-vec for this scope")
            return None
        t0 = time.monotonic()
        mat = np.empty((n, dim), dtype=np.float32)
        ids: list = [None] * n
        i = 0
        for pid, emb in conn.execute("SELECT passage_id, embedding FROM vec.passages_vec"):
            mat[i] = np.frombuffer(emb, dtype=np.float32)
            ids[i] = pid
            i += 1
        if i != n:                      # the index changed mid-read; use what we got
            mat, ids = mat[:i], ids[:i]
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = (mat / norms).astype(np.float32, copy=False)
        idx = DenseIndex(mat, ids)
        log(f"[dense] resident index loaded: n={idx.n} dim={idx.dim} float32 "
            f"bytes_mb={mat.nbytes / 1e6:.0f} in {time.monotonic() - t0:.1f}s")
        return idx
    except Exception as exc:  # noqa: BLE001 - any failure falls back to sqlite-vec, never fatal
        log(f"[dense] resident load failed ({type(exc).__name__}: {exc}); keeping sqlite-vec")
        return None
