"""Check that the in-place dense normalization is bit-identical to the old formula on a real index.

Reads every vector from one vectors.db (read-only), normalizes one copy with the pre-v2 formula
and another with retrieve.dense.normalize_rows, and compares them with np.array_equal and byte
equality. Prints one JSON line. Needs about three times the matrix size in memory.

    python scripts/v2/check_dense_identity.py --index PATH [--label NAME]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time

import numpy as np
import sqlite_vec

from archive_debugger.retrieve.dense import normalize_rows


def load_matrix(index_path: str) -> np.ndarray:
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    n = conn.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0]
    first = conn.execute("SELECT embedding FROM passages_vec LIMIT 1").fetchone()[0]
    dim = np.frombuffer(first, dtype=np.float32).shape[0]
    mat = np.empty((n, dim), dtype=np.float32)
    i = 0
    for (emb,) in conn.execute("SELECT embedding FROM passages_vec"):
        mat[i] = np.frombuffer(emb, dtype=np.float32)
        i += 1
    conn.close()
    return mat[:i]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", required=True, help="path to a vectors.db")
    parser.add_argument("--label", default="", help="name to print with the result")
    args = parser.parse_args(argv)
    t0 = time.monotonic()
    raw = load_matrix(args.index)
    old_norms = np.linalg.norm(raw, axis=1, keepdims=True)
    old_norms[old_norms == 0] = 1.0
    old = (raw / old_norms).astype(np.float32, copy=False)
    del old_norms
    new = normalize_rows(raw)
    equal = bool(np.array_equal(old, new))
    same_bytes = hashlib.sha256(old.tobytes()).hexdigest() == hashlib.sha256(new.tobytes()).hexdigest()
    print(json.dumps({"label": args.label, "index": args.index, "rows": int(new.shape[0]), "dim": int(new.shape[1]),
                      "matrix_bytes": int(new.nbytes), "array_equal": equal, "bytes_equal": same_bytes,
                      "seconds": round(time.monotonic() - t0, 1)}))
    return 0 if equal and same_bytes else 1


if __name__ == "__main__":
    sys.exit(main())
