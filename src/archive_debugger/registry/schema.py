"""The registry's tables. Every row that comes from a source names it; every derived value names its
method; dates of different kinds live in separate rows and never overwrite each other."""
from __future__ import annotations

REGISTRY_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS archives (
  archive_id TEXT PRIMARY KEY,            -- "ia"
  name TEXT NOT NULL,
  url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
  collection_id TEXT PRIMARY KEY,         -- "ia:governmentpublications"
  archive_id TEXT NOT NULL REFERENCES archives(archive_id),
  name TEXT NOT NULL,
  role TEXT NOT NULL                      -- "source" (fetched whole) or "membership" (named by a record)
);

CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,                -- "ia:<identifier>"
  archive_id TEXT NOT NULL REFERENCES archives(archive_id),
  identifier TEXT NOT NULL,
  title TEXT, creator_raw TEXT, publisher_raw TEXT, language TEXT, mediatype TEXT,
  imagecount INTEGER,                     -- scanned pages, from the catalogue
  issuer TEXT, issuer_method TEXT,        -- normalized by config/issuer_aliases.csv
  jurisdiction TEXT, jurisdiction_method TEXT,
  record_sha256 TEXT NOT NULL,            -- the catalogue record as fetched
  first_seen TEXT NOT NULL,
  UNIQUE (archive_id, identifier)
);

CREATE TABLE IF NOT EXISTS document_collections (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  PRIMARY KEY (doc_id, collection_id)
);

CREATE TABLE IF NOT EXISTS licences (
  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
  licence_url TEXT,                       -- as the catalogue states it, or NULL
  rights TEXT,                            -- as the catalogue states it, or NULL
  note TEXT NOT NULL                      -- what the project may do: "catalogue terms only" until reviewed
);

CREATE TABLE IF NOT EXISTS dates (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  kind TEXT NOT NULL,                     -- "catalogue" | "derived" | "capture" | "added"
  raw TEXT, year INTEGER,
  method TEXT NOT NULL,                   -- exact | range | partial | unknown | title_extracted | read_from_page ...
  evidence TEXT,                          -- the line or field the date was read from
  PRIMARY KEY (doc_id, kind, method)
);

CREATE TABLE IF NOT EXISTS versions (
  version_id TEXT PRIMARY KEY,            -- "ia:<identifier>@<kind>:<sha12>"
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  kind TEXT NOT NULL,                     -- "djvu_txt" | "corpus" | "reocr:<engine>"
  source_url TEXT, store_key TEXT,
  sha256 TEXT, bytes INTEGER,
  page_breaks INTEGER NOT NULL,           -- 1 when the text can be cut by page
  ocr_quality REAL,                       -- the version's quality proxy, or NULL
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS pages (
  page_id TEXT PRIMARY KEY,               -- "ia:<identifier>#<leaf>"
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  leaf INTEGER NOT NULL,
  printed_page TEXT,
  ocr_conf REAL
);

CREATE TABLE IF NOT EXISTS passages (
  passage_id TEXT PRIMARY KEY,            -- the corpus's own "<identifier>#<leaf>:<n>": unchanged
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  page_id TEXT REFERENCES pages(page_id),
  version_id TEXT NOT NULL REFERENCES versions(version_id),
  char_start INTEGER, char_end INTEGER,
  text_sha256 TEXT NOT NULL,
  scope TEXT                              -- the engine scope that serves it, when indexed
);

CREATE TABLE IF NOT EXISTS locators (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  page_id TEXT,
  kind TEXT NOT NULL,                     -- "details" | "page" | "page_image" | "djvu_txt"
  url TEXT NOT NULL,
  PRIMARY KEY (doc_id, kind, url)
);

CREATE TABLE IF NOT EXISTS coverage (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  state TEXT NOT NULL,                    -- known | text_fetched | indexed | verified | absent
  scope TEXT NOT NULL DEFAULT '',         -- which engine or audit, when it applies
  since TEXT NOT NULL,
  PRIMARY KEY (doc_id, state, scope)
);

CREATE TABLE IF NOT EXISTS governance (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  policy_id TEXT NOT NULL,
  restrict TEXT NOT NULL,                 -- JSON list: retrieve, generate, export
  authority TEXT NOT NULL,
  PRIMARY KEY (doc_id, policy_id)
);

CREATE TABLE IF NOT EXISTS audit_trail (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,                    -- the script and its version, or a person
  action TEXT NOT NULL,
  target TEXT,
  detail TEXT
);

CREATE TRIGGER IF NOT EXISTS audit_trail_append_only_update BEFORE UPDATE ON audit_trail
BEGIN SELECT RAISE(ABORT, 'the audit trail is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_trail_append_only_delete BEFORE DELETE ON audit_trail
BEGIN SELECT RAISE(ABORT, 'the audit trail is append-only'); END;

CREATE INDEX IF NOT EXISTS documents_jurisdiction ON documents(jurisdiction);
CREATE INDEX IF NOT EXISTS dates_year ON dates(kind, year);
CREATE INDEX IF NOT EXISTS passages_doc ON passages(doc_id);
CREATE INDEX IF NOT EXISTS coverage_state ON coverage(state);
"""

COVERAGE_STATES = ("known", "text_fetched", "indexed", "verified", "absent")
