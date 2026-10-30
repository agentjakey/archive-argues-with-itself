"""Build a scope's precomputed dense artifacts and gate them: byte-identical to the resident matrix
the server builds row by row from the same vectors database.

Writes <index dir>/dense/<index stem>.{matrix.npy,ids.npy,dense.json} beside the given vectors
database, then reads the artifacts back and compares them with a fresh row-by-row build
(np.array_equal and equal bytes for the matrix, equal lists for the ids). Prints one JSON line with
the sizes, sha256 and both load times. Exit 1 if the gate fails; the artifacts are then deleted so
a failed build can never be published.

The vectors database must be the published file: the manifest records its sha256, and the script
refuses an index whose sha256 differs from config/scopes.toml for the scope.

    python scripts/v2/build_dense_artifacts.py --scope pilot --index C:/civic-measure/src/index/vectors.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import sqlite_vec

from archive_debugger.api.cache import canonical_data_sha256
from archive_debugger.retrieve import dense


def open_index(index: Path) -> sqlite3.Connection:
    conn = sqlite3.connect("file::memory:", uri=True)   # uri=True so ATTACH accepts a read-only URI
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("ATTACH DATABASE ? AS vec", (f"file:{index.resolve().as_posix()}?mode=ro",))
    return conn


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", required=True)
    parser.add_argument("--index", required=True, type=Path, help="the published vectors database")
    args = parser.parse_args(argv)

    expected = canonical_data_sha256(args.scope)["index"]
    actual = dense.file_sha256(args.index)
    if actual != expected:
        print(f"refusing: {args.index} has sha256 {actual[:16]}..., the published index is {expected[:16]}...",
              file=sys.stderr)
        return 2

    conn = open_index(args.index)
    t0 = time.monotonic()
    manifest = dense.build_artifacts(conn, args.index, log=lambda _m: None)
    build_s = time.monotonic() - t0
    paths = dense.artifact_paths(args.index)

    t0 = time.monotonic()
    want_mat, want_ids = dense.read_rows(conn)
    rows_s = time.monotonic() - t0
    t0 = time.monotonic()
    got_mat, got_ids = dense.load_artifacts(args.index, manifest)
    npy_s = time.monotonic() - t0
    conn.close()

    identical = (np.array_equal(got_mat, want_mat) and got_mat.tobytes() == want_mat.tobytes()
                 and got_ids == want_ids)
    record = {
        "scope": args.scope, "index_sha256": actual, "rows": manifest["rows"], "dim": manifest["dim"],
        "matrix_bytes": paths["matrix"].stat().st_size, "ids_bytes": paths["ids"].stat().st_size,
        "matrix_sha256": manifest["matrix_sha256"], "ids_sha256": manifest["ids_sha256"],
        "manifest_sha256": dense.file_sha256(paths["manifest"]),
        "byte_identical": identical, "build_seconds": round(build_s, 2),
        "load_rows_seconds": round(rows_s, 2), "load_npy_seconds": round(npy_s, 2),
    }
    print(json.dumps(record))
    if not identical:
        for path in paths.values():
            path.unlink(missing_ok=True)
        print("gate failed: artifacts differ from the row-by-row matrix; deleted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
