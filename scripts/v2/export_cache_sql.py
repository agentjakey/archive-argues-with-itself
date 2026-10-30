"""Write the SQL that seeds the D1 answer cache with the curated rows of local v2 caches.

Only rows marked curated (seed and story questions) are written; visitor rows never leave this
machine and the old v1 files are deleted with the Railway volume (docs/v2/PRIVACY.md). The output
is applied by the account owner:

    python scripts/v2/export_cache_sql.py --cache data/cache/answers.db \
        --cache data/exploration/microlog/cache/answers.db --out build/d1_curated.sql
    npx wrangler d1 execute DB --remote --env staging --file ../../build/d1_curated.sql
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

COLUMNS = ("key", "scope", "curated", "question", "response_json", "extras_version", "model",
           "prompt_sha256", "context", "created_at", "expires_at")


def literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", action="append", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    lines = []
    for path in args.cache:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM answers_v2 WHERE curated = 1 ORDER BY key").fetchall()
        conn.close()
        for row in rows:
            values = ", ".join(literal(v) for v in row)
            lines.append(f"INSERT OR REPLACE INTO answers_v2 ({', '.join(COLUMNS)}) VALUES ({values});")
        print(f"{path}: {len(rows)} curated rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} statements to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
