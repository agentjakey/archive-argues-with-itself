-- The answer cache (format v2, docs/formats/answer_cache.md) and the daily model budget.
-- Same columns as the engine's local cache (src/archive_debugger/api/cache.py SCHEMA).
CREATE TABLE IF NOT EXISTS answers_v2 (
    key            TEXT PRIMARY KEY,
    scope          TEXT NOT NULL,
    curated        INTEGER NOT NULL,
    question       TEXT,
    response_json  TEXT NOT NULL,
    extras_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_sha256  TEXT NOT NULL,
    context        TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    expires_at     TEXT
);
CREATE INDEX IF NOT EXISTS answers_v2_expires ON answers_v2 (expires_at);

CREATE TABLE IF NOT EXISTS model_budget (
    day   TEXT PRIMARY KEY,
    calls INTEGER NOT NULL
);
