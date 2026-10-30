# Answer cache, format v2

Writers: the engine (`src/archive_debugger/api/cache.py`, local SQLite or the engine Worker's cache
route). Readers: the engine, the engine Worker (`worker/engine/src/cache.ts`), the site data export
(`scripts/v2/export_site_data.py`, curated rows only). A change to anything here changes all of
them in the same commit, regenerates `config/cache_key_vectors.json`, and re-exports
`worker/engine/src/generated/engine_config.json`.

## Key

```
context = sha256 of Python json.dumps(sort_keys=True, ensure_ascii=False) of
    { scope, data_sha256: {db, index} (from config/scopes.toml), retrieve: the retrieve config
      without db_path and index_path, provider, model, prompt_sha256, top_k, temperature }
key = sha256 of canonical JSON (sorted keys, no spaces, non-ASCII kept) of
    { "v": "2", "context": context, "question": normalize(question), "filters": canonical(filters) }
```

- `normalize`: lone UTF-16 surrogates become U+FFFD; Unicode NFC; U+0000-U+001F and U+007F become
  spaces; runs of spaces collapse; leading and trailing spaces are removed. Case and every other
  character are kept.
- `canonical(filters)`: `period`, `jurisdiction` and `doc_type` as normalized strings when not
  empty; `min_ocr` as a string with four decimals when set and not zero; other keys ignored.
- The Worker keys only the configured provider and model of each scope (from the generated
  config). A request for another provider or model, or with `nocache`, goes to the engine.

## Row (table `answers_v2`, the same in SQLite and D1)

| column | content |
| --- | --- |
| `key` | the key above, 64 hex characters |
| `scope` | `pilot` or `microlog` |
| `curated` | 1 for a seed or story question, else 0 |
| `question` | the normalized question for a curated row; NULL otherwise |
| `response_json` | the served response without `answer.cached` and `editorial_notes`; date methods and care flags included |
| `extras_version` | the engine's `EXTRAS_VERSION` (a hash of the code that adds date methods and care flags) when stored |
| `model`, `prompt_sha256`, `context` | what produced the answer |
| `created_at` | ISO 8601 UTC, seconds, `+00:00` |
| `expires_at` | NULL for a curated row; `created_at` + 180 days otherwise |

A row that is not curated keeps no words of the question. In its `response_json`, the coverage
block's `salient_terms` and `uncovered_terms` are replaced by
`terms_withheld: {salient_count, uncovered_index}`; whoever serves the row restores the terms from
the asker's own question (`restore_terms` / `restoreTerms`) and treats a count mismatch as a miss.

## Serving a row

Add `answer.cached = {created_at}` and the dated editorial notes for that scope and exact question
(`config/editorial_notes.json`, `cached_only` notes included). The Worker serves a row only when its
`extras_version` is the current one; otherwise the engine recomputes the date methods and care flags
and rewrites the row under its original `created_at`.

## Over HTTP

The engine Worker serves a stored answer with a strong `ETag` (the first 32 hex characters of the
sha256 of the exact body, notes included) and `Cache-Control: public, max-age=0, must-revalidate`; a
request whose `If-None-Match` carries that ETag gets `304 Not Modified` and no body. An answer the
engine has just written is served with `Cache-Control: no-store`.

## Expiry

Rows with `expires_at` in the past are never served, and a daily job deletes them (the Worker's
cron at 04:00 UTC; the local cache when its file is opened).
