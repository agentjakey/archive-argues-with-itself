# Site data shards and the release manifest, format v1

Writer: `scripts/v2/export_site_data.py` (into `site/data`, committed). Readers: the web app in a
static release (`web/src/lib/staticData.ts`) and the release gates
(`scripts/v2/build_release.py`). Everything here is computed by the engine itself from the
published data, read-only; nothing depends on a visitor's question and no visitor data is included.

## Files (under `/data` in a release)

| path | content |
| --- | --- |
| `scopes.json` | the engine's `/scopes` response: the served scopes, their display facts, the crisis lines |
| `editorial_notes.json` | `config/editorial_notes.json` as served by `/editorial-notes` |
| `export.json` | `{format_version, scopes: {<scope>: {recorded, missing: [labels]}}}` |
| `<scope>/health.json` | `{provider, model, corpus}` from `/health` |
| `<scope>/examples.json` | `/examples`: the seed questions |
| `<scope>/stories.json` | `/stories`: each story with its pinned pages, comparability block, surfaces, notes and care flag |
| `<scope>/answers/index.json` | `{format_version, scope, data_sha256, answers: [entry]}` |
| `<scope>/answers/<label>.json` | the recorded answer, exactly as the engine served it from its cache (`answer.cached` set, dated notes attached) |
| `<scope>/coverage/<label>.json` | `/coverage` for that question and its filters |

An index entry: `{label ("seed:q001" or "story:<id>"), question, normalized_question, filters
(canonical, as in answer_cache.md), file (or null when there is no recorded answer), coverage}`.
The web app finds a recorded answer by comparing the normalized question and canonical filters, so
a typed or linked seed question is answered from the shards too. Labels become file names with
`:` replaced by `-`.

## Release manifest (`/release-manifest.json`)

`{release_id, git_commit, built_at, api_origin, data_export (export.json), files: {<path>:
{sha256, bytes}}}` for every file in the release except the manifest. The gates read the release
as it will be published and refuse it when any file differs from the manifest. A release is live
when the site Worker's deployment points at its version; earlier versions remain for rollback.
