"""civic.db schema (Phase 3).

Creates the tables. No OCR parsing, no normalization, no coordinate storage.

N3: there are no bbox/coordinate columns anywhere. has_word_coords is a boolean
capability flag only (which items COULD support word-level precision later); the
coordinates themselves are never stored in the core build.

The normalized columns on items (issuer_norm, jurisdiction_norm, date_norm, year,
decade, dated, doc_type_norm, and their *_method companions) are created here but
left NULL. Phase 5 is the single source of truth that populates them.
"""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS items (
    item_id              TEXT PRIMARY KEY,   -- the IA identifier; deep links use this
    -- raw harvest columns
    title                TEXT,
    creator_raw          TEXT,               -- preserved separately from publisher; issuer_norm
    publisher_raw        TEXT,               -- is derived from both in Phase 5
    date_raw             TEXT,               -- raw IA date string
    collection_raw       TEXT,               -- full IA collection list (JSON) for coverage
    language             TEXT,
    mediatype            TEXT,
    ocr_format           TEXT,
    ocr_engine           TEXT,               -- nullable (unknown for some items)
    has_word_coords      INTEGER,            -- boolean capability flag only (N3)
    has_printed_page_map INTEGER,
    page_count           INTEGER,
    ocr_file_ref         TEXT,               -- content-address of the cached derivative
    details_url          TEXT,
    license              TEXT,
    ingest_ts            TEXT,
    -- Phase-5 normalized outputs: created here, left NULL until Phase 5 populates them.
    issuer_norm          TEXT,
    issuer_method        TEXT,
    jurisdiction_norm    TEXT,
    jurisdiction_method  TEXT,
    date_norm            TEXT,
    year                 INTEGER,
    decade               TEXT,
    dated                INTEGER,
    date_method          TEXT,
    doc_type_norm        TEXT,
    doc_type_method      TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    page_id       TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL REFERENCES items(item_id),
    leaf_index    INTEGER,
    printed_page  TEXT,                       -- nullable; the printed page label
    char_count    INTEGER,
    ocr_conf_mean REAL,                       -- nullable
    has_text      INTEGER,
    section_class  TEXT,                      -- Phase 13: front | body | back (ingest.sections); NULL = unclassified
    section_method TEXT                       -- the deciding signal, for eyeballing samples
);
CREATE INDEX IF NOT EXISTS idx_pages_item ON pages(item_id);

CREATE TABLE IF NOT EXISTS passages (
    passage_id    TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL REFERENCES items(item_id),
    page_id       TEXT NOT NULL REFERENCES pages(page_id),
    leaf_index    INTEGER,
    char_start    INTEGER,
    char_end      INTEGER,
    text          TEXT,
    token_count   INTEGER,
    ocr_conf_mean REAL,                       -- nullable
    ocr_quality   TEXT,
    embedding_id  TEXT                        -- nullable until embeddings exist
);
CREATE INDEX IF NOT EXISTS idx_passages_item ON passages(item_id);
CREATE INDEX IF NOT EXISTS idx_passages_page ON passages(page_id);

-- Full-text search over passage text, external-content against passages. Kept in
-- sync by triggers. No coordinates are indexed.
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    text,
    content='passages',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS passages_ai AFTER INSERT ON passages BEGIN
    INSERT INTO passages_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS passages_ad AFTER DELETE ON passages BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS passages_au AFTER UPDATE ON passages BEGIN
    INSERT INTO passages_fts(passages_fts, rowid, text) VALUES('delete', old.rowid, old.text);
    INSERT INTO passages_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS coverage_cells (
    cell_id         INTEGER PRIMARY KEY,
    period          TEXT,   -- a year/decade OR the literal 'undated'|'pre-1960'|'post-2009'
    jurisdiction    TEXT,
    issuer          TEXT,
    doc_type        TEXT,
    item_count      INTEGER,
    page_count      INTEGER,
    passage_count   INTEGER,
    undated_count   INTEGER,
    ocr_conf_bucket TEXT,
    ocr_conf_count  INTEGER
);

CREATE TABLE IF NOT EXISTS eval_questions (
    qid                    TEXT PRIMARY KEY,
    text                   TEXT,
    topic                  TEXT,
    qtype                  TEXT,   -- factual|temporal_comparison|abstention_probe (candidate; nullable)
    filters_json           TEXT,   -- {period,jurisdiction,doc_type} scoping hints (candidate)
    expected_periods       TEXT,   -- DEPRECATED, unused: never populated (N4 expected-label trap)
    expected_jurisdictions TEXT,   -- DEPRECATED, unused: never populated (N4 expected-label trap)
    notes                  TEXT
);

CREATE TABLE IF NOT EXISTS eval_labels (
    qid        TEXT NOT NULL REFERENCES eval_questions(qid),
    passage_id TEXT NOT NULL REFERENCES passages(passage_id),
    relevance  INTEGER,
    PRIMARY KEY (qid, passage_id)
);

-- Per-question human verdict, kept apart from the candidate row so candidate text
-- and gold judgment never mix (N4).
CREATE TABLE IF NOT EXISTS eval_question_gold (
    qid        TEXT PRIMARY KEY REFERENCES eval_questions(qid),
    answerable INTEGER,            -- human verdict: 1 answerable, 0 should-abstain
    labeled_ts TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id      TEXT PRIMARY KEY,
    git_sha     TEXT,
    config_json TEXT,
    ts          TEXT
);

CREATE TABLE IF NOT EXISTS eval_results (
    run_id TEXT NOT NULL REFERENCES eval_runs(run_id),
    qid    TEXT NOT NULL REFERENCES eval_questions(qid),
    metric TEXT NOT NULL,
    value  REAL,
    PRIMARY KEY (run_id, qid, metric)
);

CREATE TABLE IF NOT EXISTS gaps (
    gap_id        TEXT PRIMARY KEY,
    gap_type      TEXT,
    scope         TEXT,
    metric        TEXT,
    value         REAL,
    examples_json TEXT
);
"""

# Tables expected after migration (excludes FTS shadow tables and triggers).
EXPECTED_TABLES = (
    "items",
    "pages",
    "passages",
    "passages_fts",
    "coverage_cells",
    "eval_questions",
    "eval_labels",
    "eval_question_gold",
    "eval_runs",
    "eval_results",
    "gaps",
)


def _ensure_columns(conn: sqlite3.Connection, table: str, coldefs: tuple) -> None:
    """Idempotently ADD any missing columns to an existing table. CREATE TABLE IF
    NOT EXISTS cannot add columns to a table that already exists, so a live
    civic.db needs this to gain qtype/filters_json."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in coldefs:
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, the FTS table, and its sync triggers, then run
    idempotent column migrations for tables that predate a column."""
    conn.executescript(SCHEMA_SQL)
    _ensure_columns(conn, "eval_questions", (("qtype", "qtype TEXT"), ("filters_json", "filters_json TEXT")))
    _ensure_columns(conn, "pages", (("section_class", "section_class TEXT"), ("section_method", "section_method TEXT")))
    conn.commit()
