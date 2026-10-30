"""Build a scope's precomputed corpus facts, a release file the server loads instead of running the
aggregate queries when it opens the scope (about 11 s for the pilot).

Refuses a database whose sha256 is not the published one in config/scopes.toml. Writes
<database stem>.facts.json beside the database, then checks that the file loads back to exactly
what the server computes from the database, and prints its sha256 and size for the registry's
[scopes.<scope>.facts] block.

    python scripts/v2/build_scope_facts.py --scope pilot --db C:/civic-measure/src/civic.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", required=True)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args(argv)

    from archive_debugger import release_files, scopes
    from archive_debugger.api import app as app_mod
    from archive_debugger.api.cache import canonical_data_sha256
    from archive_debugger.retrieve.dense import file_sha256

    published = canonical_data_sha256(args.scope)["db"]
    actual = file_sha256(args.db)
    if actual != published:
        print(f"refusing: {args.db} is not the published database for {args.scope}", file=sys.stderr)
        return 2
    resolved = scopes.resolve_scope(args.scope)
    window = app_mod._pilot_window(Path(resolved.config_path))
    conn = sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro", uri=True)
    t0 = time.monotonic()
    doc = app_mod.facts_document(args.scope, conn, published, window)
    compute_s = time.monotonic() - t0
    out = release_files.facts_path(args.db)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    t0 = time.monotonic()
    loaded = app_mod.load_or_compute_data_facts(args.scope, conn, args.db, window)
    load_s = time.monotonic() - t0
    conn.close()
    if loaded != {"corpus": doc["corpus"], "composition": doc["composition"]}:
        out.unlink()
        print("gate failed: the facts file does not load back to the computed facts; deleted", file=sys.stderr)
        return 1
    print(json.dumps({"scope": args.scope, "file": str(out), "bytes": out.stat().st_size,
                      "sha256": file_sha256(out), "facts_version": doc["facts_version"],
                      "compute_seconds": round(compute_s, 2), "load_seconds": round(load_s, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
