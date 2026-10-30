"""Resident in-memory dense retrieval (A4), behind CIVIC_DENSE_BACKEND=numpy (default sqlite).

The default dense leg is a per-row vec_distance_cosine scan over the whole sqlite-vec index, which is
slow on a shared vCPU and, when the index is not held resident, re-reads it on every query. This
module holds one scope's vectors resident as a normalized float32 matrix and does the dense leg as a
single vectorized exact cosine (one matvec + argpartition top-k). It is exact, not approximate: the
rows are L2-normalized once at load and the query at search time, both in float32, so the returned
candidate SET matches the sqlite-vec scan; only tie order at identical distances may differ.

Boundaries: read-only, local-file only (no network, N1). The matrix comes from precomputed release
artifacts beside the index when they are present and describe it (build_artifacts below: the same
rows, in the same order, normalized the same way, saved as .npy), else from the already-open
vec.passages_vec one row at a time. Generation, the prompt, the abstention rule, BM25, RRF fusion,
top_k, and the passage-id mapping are all unchanged; only the dense candidate leg is replaced.
Enabling the flag can never OOM or break serving: the load is guarded by the container memory limit
and any failure falls back to sqlite-vec.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

ENV_BACKEND = "CIVIC_DENSE_BACKEND"   # "sqlite" (default) | "numpy"
ENV_HEADROOM_MB = "CIVIC_DENSE_HEADROOM_MB"
# Memory the guard keeps free beyond the process's anonymous memory and the new matrix: room for
# request-time allocations, the embedding model's working buffers, and SQLite's page cache for the
# full-text and passage tables. An explicit amount rather than a share of the limit.
DEFAULT_HEADROOM_MB = 1024
# Python-side cost per row of the id list plus the passage_id -> row dict. Measured with tracemalloc on
# the published databases (2026-10-29): 147.7 bytes/row on the pilot, 138.2 on microlog; rounded up.
_ID_BYTES_PER_ROW = 160
ARTIFACT_VERSION = 1


def resident_bytes(n: int, dim: int) -> int:
    """Peak bytes a resident load adds: the float32 matrix (normalized in place, so held once), the
    per-row norms, and the id list and lookup dict."""
    return n * dim * 4 + n * 4 + n * _ID_BYTES_PER_ROW

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


def _anon_bytes() -> Optional[int]:
    """The process's anonymous resident memory (RssAnon): memory it owns and the kernel cannot drop.
    VmRSS is not used: it also counts the pages of every memory-mapped data file, which are page
    cache the kernel reclaims under pressure, and counting them refused a matrix that fit (known
    error 14, docs/v2/BASELINE_AUDIT.md). None where /proc is not available."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("RssAnon:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def headroom_bytes() -> int:
    """CIVIC_DENSE_HEADROOM_MB, or DEFAULT_HEADROOM_MB when it is unset or not a whole number."""
    raw = os.environ.get(ENV_HEADROOM_MB, "").strip()
    try:
        return int(raw) * 1024 * 1024 if raw else DEFAULT_HEADROOM_MB * 1024 * 1024
    except ValueError:
        return DEFAULT_HEADROOM_MB * 1024 * 1024


def fits(est: int, *, limit: Optional[int], anon: Optional[int], headroom: int) -> bool:
    """True when anonymous memory plus the new matrix plus the headroom stays within the limit, or
    when either number cannot be read (no container limit, as on a development machine)."""
    if limit is None or anon is None:
        return True
    return anon + est + headroom <= limit


_NORM_BLOCK_ROWS = 16384   # rows per block when computing norms (a ~25 MB temporary at dim 384)


def normalize_rows(mat: np.ndarray) -> np.ndarray:
    """L2-normalize each row of a float32 matrix in place and return it. Bit-identical to the earlier
    (mat / np.linalg.norm(mat, axis=1, keepdims=True)).astype(float32), but without a second full
    matrix: np.linalg.norm squares its whole input into a temporary, so the norms are computed one
    block of rows at a time (each row's norm is reduced on its own, so blocking does not change it),
    and the division writes back into mat. Zero rows stay zero."""
    n = mat.shape[0]
    norms = np.empty((n, 1), dtype=mat.dtype)
    for start in range(0, n, _NORM_BLOCK_ROWS):
        stop = min(start + _NORM_BLOCK_ROWS, n)
        norms[start:stop] = np.linalg.norm(mat[start:stop], axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    np.divide(mat, norms, out=mat)
    return mat


def read_rows(conn) -> tuple[np.ndarray, list]:
    """Every vector of vec.passages_vec, normalized, with its passage id, in the table's own order.
    The one definition of the resident matrix: the serving load and the artifact build both use it."""
    n = conn.execute("SELECT COUNT(*) FROM vec.passages_vec").fetchone()[0]
    first = conn.execute("SELECT embedding FROM vec.passages_vec LIMIT 1").fetchone()
    dim = int(np.frombuffer(first[0], dtype=np.float32).shape[0])
    mat = np.empty((n, dim), dtype=np.float32)
    ids: list = [None] * n
    i = 0
    for pid, emb in conn.execute("SELECT passage_id, embedding FROM vec.passages_vec"):
        mat[i] = np.frombuffer(emb, dtype=np.float32)
        ids[i] = pid
        i += 1
    if i != n:                      # the index changed mid-read; use what we got
        mat, ids = mat[:i], ids[:i]
    return normalize_rows(mat), ids


# --- precomputed artifacts ------------------------------------------------------------------------

def artifact_paths(index_file: Path) -> dict:
    """Where a scope's dense artifacts sit: a dense/ directory beside its vectors database."""
    folder = Path(index_file).parent / "dense"
    stem = Path(index_file).stem
    return {"matrix": folder / f"{stem}.matrix.npy",
            "ids": folder / f"{stem}.ids.npy",
            "manifest": folder / f"{stem}.dense.json"}


def stub_sidecar(index_file: Path) -> Path:
    return Path(str(index_file) + ".stub.json")


def stub_target(index_file: Path) -> Optional[str]:
    """For a stand-in index written by the boot (provision.write_stub_index): the sha256 of the
    published index it replaces. None for a real index."""
    sidecar = stub_sidecar(index_file)
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")).get("stands_in_for_index_sha256")
    except (OSError, ValueError):
        return None


def _attached_index_file(conn) -> Optional[Path]:
    """The vectors database attached to a Retriever's connection as 'vec'."""
    for _seq, name, file in conn.execute("PRAGMA database_list"):
        if name == "vec" and file:
            return Path(file)
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifacts(conn, index_file: Path, *, log: Log = print) -> dict:
    """Write the normalized matrix and the ids as .npy files beside the index, plus a manifest with
    their sha256 and the index file's size and sha256. Ids are stored as fixed-width ASCII bytes, so
    reading them back never involves pickle."""
    paths = artifact_paths(index_file)
    paths["matrix"].parent.mkdir(parents=True, exist_ok=True)
    mat, ids = read_rows(conn)
    encoded = [pid.encode("ascii") for pid in ids]
    width = max((len(e) for e in encoded), default=1)
    np.save(paths["matrix"], mat, allow_pickle=False)
    np.save(paths["ids"], np.array(encoded, dtype=f"S{width}"), allow_pickle=False)
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "rows": int(mat.shape[0]), "dim": int(mat.shape[1]), "dtype": "float32",
        "index_file": Path(index_file).name, "index_bytes": Path(index_file).stat().st_size,
        "index_sha256": file_sha256(Path(index_file)),
        "matrix_sha256": file_sha256(paths["matrix"]), "ids_sha256": file_sha256(paths["ids"]),
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    log(f"[dense] artifacts written: rows={manifest['rows']} dim={manifest['dim']} to {paths['matrix'].parent}")
    return manifest


def _release_file_cache(fh) -> None:
    """Drop a just-read file's pages from the page cache (Linux), so a loaded artifact is held once,
    in the process, and not a second time as page cache charged to the container."""
    advise = getattr(os, "posix_fadvise", None)
    if advise is not None:
        try:
            advise(fh.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        except OSError:
            pass


def _load_npy(path: Path) -> np.ndarray:
    with open(path, "rb") as fh:
        arr = np.load(fh, allow_pickle=False)
        _release_file_cache(fh)
    return arr


def usable_artifacts(index_file: Optional[Path]) -> Optional[dict]:
    """The artifact manifest when all three files are present and the manifest describes this index:
    the same file name and size for a real index, or, for the boot's stand-in index, the published
    index sha256 that its sidecar names. The boot checks every downloaded file's sha256 against the
    release."""
    if index_file is None:
        return None
    paths = artifact_paths(index_file)
    if not all(p.exists() for p in paths.values()):
        return None
    try:
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("artifact_version") != ARTIFACT_VERSION or manifest.get("index_file") != Path(index_file).name:
        return None
    stands_in_for = stub_target(Path(index_file))
    if stands_in_for is not None:
        return manifest if stands_in_for == manifest.get("index_sha256") else None
    return manifest if manifest.get("index_bytes") == Path(index_file).stat().st_size else None


def load_artifacts(index_file: Path, manifest: dict) -> tuple[np.ndarray, list]:
    """The matrix and ids from the .npy artifacts, checked against the manifest's shape."""
    paths = artifact_paths(index_file)
    mat = _load_npy(paths["matrix"])
    raw_ids = _load_npy(paths["ids"])
    if mat.shape != (manifest["rows"], manifest["dim"]) or mat.dtype != np.float32 or raw_ids.shape[0] != mat.shape[0]:
        raise ValueError(f"dense artifacts do not match their manifest: {mat.shape} {mat.dtype} ids={raw_ids.shape}")
    return mat, [b.decode("ascii") for b in raw_ids.tolist()]


def load_if_enabled(conn, *, log: Log = print) -> Optional[DenseIndex]:
    """Build a resident DenseIndex when CIVIC_DENSE_BACKEND=numpy and it fits under the container
    memory limit; otherwise None, so the caller keeps the sqlite-vec leg. The matrix comes from the
    precomputed artifacts when they describe the attached index, else from vec.passages_vec. Never
    raises: any failure logs and returns None, so enabling the flag can never OOM the box or break
    serving (degrade, never error). conn must have the vec database attached (the Retriever's own
    connection)."""
    if not backend_is_numpy():
        return None
    try:
        index_file = _attached_index_file(conn)
        manifest = usable_artifacts(index_file)
        if manifest is not None:
            n, dim = manifest["rows"], manifest["dim"]
        else:
            n = conn.execute("SELECT COUNT(*) FROM vec.passages_vec").fetchone()[0]
            if n == 0:
                return None
            first = conn.execute("SELECT embedding FROM vec.passages_vec LIMIT 1").fetchone()
            dim = int(np.frombuffer(first[0], dtype=np.float32).shape[0])
        est = resident_bytes(n, dim)
        limit, anon, headroom = _container_limit(), _anon_bytes(), headroom_bytes()
        if not fits(est, limit=limit, anon=anon, headroom=headroom):
            log(f"[dense] would not fit: est_mb={est / 1e6:.0f} anon_mb={anon / 1e6:.0f} "
                f"headroom_mb={headroom / 1e6:.0f} limit_mb={limit / 1e6:.0f}; keeping sqlite-vec for this scope")
            return None
        t0 = time.monotonic()
        if manifest is not None:
            mat, ids = load_artifacts(index_file, manifest)
            source = "artifacts"
        else:
            mat, ids = read_rows(conn)
            source = "sqlite rows"
        idx = DenseIndex(mat, ids)
        log(f"[dense] resident index loaded from {source}: n={idx.n} dim={idx.dim} float32 "
            f"bytes_mb={mat.nbytes / 1e6:.0f} in {time.monotonic() - t0:.1f}s")
        return idx
    except Exception as exc:  # noqa: BLE001 - any failure falls back to sqlite-vec, never fatal
        log(f"[dense] resident load failed ({type(exc).__name__}: {exc}); keeping sqlite-vec")
        return None
