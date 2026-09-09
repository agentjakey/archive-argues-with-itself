"""Thin data-access layer over civic.db.

Connection setup, migration, and small helpers. No OCR parsing, no normalization,
no network. The DB path is read from config/pilot.toml [index].db_path.
"""

from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path

from archive_debugger.ingest import schema


def resolve_db_path(config_path: Path) -> Path:
    """Read [index].db_path from the pilot config."""
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    return Path(raw["index"]["db_path"])


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    schema.create_schema(conn)


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) and migrate the database."""
    conn = connect(db_path)
    migrate(conn)
    return conn


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]
