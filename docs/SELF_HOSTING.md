# Running your own copy on Cloudflare

How the hosted version runs, and how to run the same thing on your own Cloudflare account. The
hosted site is https://archiveargues.org.

## The parts

| Part | What it is | Cost when nobody is using it |
| --- | --- | --- |
| The site | a Worker with static assets only (`worker/site`): the reading room, the stories, the recorded answers to the example questions, and the data shards | nothing: static requests are free |
| The engine Worker | `worker/engine`: the only way to reach the engine | nothing: billed per request |
| The engine | the FastAPI app in a Cloudflare container, started by the engine Worker's Durable Object and stopped after a few idle minutes | nothing while it sleeps |
| The answer cache and daily model budget | D1 | within the free allowance |
| The corpus, the vectors and the derived release files | a private R2 bucket | storage only |

A page view touches only the site. An example question or a story is answered from the release's
recorded answers. Any other question goes to the engine Worker, which serves a stored answer from D1
without waking the engine when it has one; otherwise it checks Turnstile, a per-visitor rate limit
and the daily model budget, and wakes the engine. While the engine starts, the site shows how far it
has got and asks again on its own when it is ready.

## What you need

A Cloudflare account on the Workers Paid plan (containers need it), Docker (wrangler builds the
engine image locally), Node 20 or later, Python 3.11, an Anthropic API key, and the published data:
the corpus and vectors databases from the data release, plus the derived release files described
below.

## Data on R2

Every file a collection publishes, its R2 key, its sha256 and its place on disk come from its entry
in `config/scopes.toml` (`src/archive_debugger/release_files.py`). Upload the databases with
`scripts/upload_scopes_to_r2.py` and the derived files (the dense artifacts and the corpus facts)
with `scripts/v2/upload_artifacts.py --src <folder of verified files>`. Both check every file against
the published sha256 first. The bucket stays private; the engine reads it only through the engine
Worker's R2 binding, so the container holds no R2 key.

The derived files are built from the published databases, never from a working copy:

- `scripts/v2/build_dense_artifacts.py`: each collection's normalized embedding matrix and passage
  ids as `.npy` files, byte-identical to the matrix the server would build row by row.
- `scripts/v2/build_scope_facts.py`: the corpus figures the site shows, so opening a collection does
  not have to compute them.

## Setting up the Workers

From `worker/engine` after `npm ci`, for an environment named `staging` (repeat with `production`):

```
npx wrangler d1 create archive-argues-cache-staging        # put the id in wrangler.jsonc
npx wrangler d1 migrations apply DB --remote --env staging
npx wrangler secret put ANTHROPIC_API_KEY --env staging
npx wrangler secret put TURNSTILE_SECRET_KEY --env staging
npx wrangler deploy --env staging --var RELEASE_ID:<release>
```

Set the data bucket's name in both `r2_buckets` entries. Create an invisible Turnstile widget for your
site's hostnames and build the site with its site key. Seed D1 with the recorded answers to the
example questions (`scripts/v2/export_cache_sql.py`, then `npx wrangler d1 execute DB --remote --file
<sql>`); only curated rows are exported.

The production environment attaches the custom domains in `worker/engine/wrangler.jsonc` and
`worker/site/wrangler.jsonc` when you deploy; your zone must be on Cloudflare.

## Releases and rollback

```
cd web; npm ci; npm run build; cd ..        # with VITE_STATIC_DATA=/data, VITE_API_BASE and VITE_TURNSTILE_SITEKEY set
python scripts/v2/build_release.py assemble --release-id <id> --api-origin https://<your engine Worker>
python scripts/v2/build_release.py gate
python scripts/v2/build_release.py publish --env <env>
python scripts/v2/build_release.py rollback --env <env> [--version <worker version id>]
```

`publish` refuses a release that fails a gate before anything is uploaded. The gates read the
release exactly as it will be served: the manifest lists every file with its sha256, the file count
and sizes fit Workers static assets, every recorded answer says when and with which model and prompt
it was generated, every citation resolves to a page in its own evidence, every dated note is
attached, no story's caption claims more than its comparability block, no retired story is featured,
and nothing looks like a secret. Going live is moving the site Worker to the new version; rollback
moves it back. Caching is described in `docs/formats/site_data.md`.

The GitHub `deploy` workflow does the same on a manual run or a `v2.*` tag, with the Cloudflare
token and account id as Actions secrets.

## Adding a collection

A collection is config plus data. Add its entry to `config/scopes.toml` (its config file, R2 keys and
sha256, `release_dir`, seed and stories files, a seed question the record cannot answer for the
"See it decline" doorway, its publisher phrase, whether it is national, and the audit whose results
describe it, if any), build and upload its derived files, and add it to `CIVIC_ENABLED_SCOPES`. The
boot, the Worker's allow list, the release tools and the site pick it up from the registry; a
collection that has not been audited shows that, never another collection's numbers.

## Design choices

- **The engine starts on demand.** The container opens its port at once and reports its stages on
  `/health` (fetching, verifying, loading, ready). It fetches its files as parallel ranged reads and
  hashes each while it arrives, so there is no second verification pass, and stops cleanly on SIGTERM
  at any stage.
- **Every file is checked before anything is served from it**, against the sha256 in
  `config/scopes.toml`: while downloading, or by a full hash when files are restored from a snapshot.
  Data baked into the image is the one exception: the registry addresses each image layer by its
  digest and verifies it on pull, and the bake script checked every file first.
- **The vectors database stays on R2.** With the in-memory dense backend the engine loads the
  precomputed matrix and writes a small stand-in for the vectors database that names the published
  index it replaces. If the matrix cannot load, the collection answers in limited mode rather than
  from keyword search alone.
- **The container uses Cloudflare's `durable_object` scheduling policy**, which is in public beta;
  the fallback is the default policy with the `@cloudflare/containers` Container class, which needs
  changes only in `worker/engine/src/container.ts` and the wrangler config.

## Privacy and costs

What is kept about questions: `docs/PRIVACY.md`. A monthly cost estimate for given awake hours and
instance size, from the published prices: `python scripts/v2/cost_estimate.py --instance standard-3
--awake-hours 1 2 6`.

## Moving from another host

`redirect/` is a tiny standard-library app that answers every request with a 301 to the same path and
query on the new domain (old `/ask?q=...` permalinks open the reading room). Deploy it in place of the
old service, with no volume, and its address keeps working.
