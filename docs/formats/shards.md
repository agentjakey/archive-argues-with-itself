# Shard plan and coverage format

## The plan (`config/shards/plan.json`)

`scripts/v2/shards.py plan` cuts the whole collection into engines of about a million passages each.
Each engine holds one jurisdiction and a run of years, so a question about a place and a period wakes
only a few of them. Code: `src/archive_debugger/shards/plan.py`.

- **Estimating size.** Passages per document are estimated from the catalogue's scanned-page count,
  times the built corpora's measured passages per page. The plan uses the upper value, 1.59, so
  shards err small. A record with no page count is counted at 72 pages, the sample's median.
- **Cutting by year.** A jurisdiction's dated documents are sorted by year and cut into consecutive
  ranges that fit. If a single year is bigger than one shard, it is split across shards, and both say
  `split_year`.
- **Undated documents** get shards of their own. An undated record never sits in a dated range.
- **Small jurisdictions.** A jurisdiction smaller than 200,000 passages shares "other" shards. Their
  `jurisdictions` field lists every place they hold.

Each shard has these fields: `shard_id`, `jurisdiction`, `jurisdictions`, `first_year`, `last_year`,
`undated`, `split_year`, `documents` (a count), `documents_sha256`, `est_passages` and
`est_wake_gb`. At 4.14 KB per passage, `est_wake_gb` is the databases plus the dense artifacts.

`data/shards/members.tsv` maps every document to exactly one shard. The plan refuses to write if any
document would sit in two.

## Coverage file (one per built shard)

Coverage files are written when a shard is built, and the router reads them before waking any
engine. Code: `src/archive_debugger/shards/coverage.py`.

| Field | Meaning |
|---|---|
| `shard_id`, `jurisdictions` | as in the plan |
| `years` | `{"<jurisdiction>\|<year or undated>": documents}` |
| `passages`, `tokens` | for collection-wide BM25: N and the total length |
| `df` | `{term: passages containing it}` for every term in two or more passages. Terms are lower-cased words without the frozen stopword list, the same as the BM25 leg |

## Routing

The router (`src/archive_debugger/shards/router.py`) has two steps.

1. **Choosing engines.** A shard is eligible when its jurisdictions and years fit the question's
   filters and at least one of the question's words occurs in it. Eligible shards are ranked by
   document frequency times the collection-wide idf, and at most three are woken. Every shard that
   is left out carries its reason: other jurisdictions, no documents in the period, none of the
   question's words, or ranked below the engines woken. An answer can then say what it did not
   search.
2. **Merging results.** Dense scores come from one model, so they are compared as they are. BM25 is
   recomputed from each candidate's query-term counts and length, using the collection's N,
   document frequencies and average length summed over all coverage files. The two rankings are
   fused by reciprocal rank with k = 60, and one model call is made on the merged top passages.

## Served shards (`config/shards/served.toml`)

Each served shard is one engine scope, and so one container in the engine Worker's split layout.
`scripts/v2/serve_shards.py register --shard <id>` writes its entry from the shard builder's
manifest on R2. The scope registry (`archive_debugger.scopes.load_registry`) reads the file
together with `config/scopes.toml`. A shard may not reuse a registered scope's name. No shard is
named in code.

| Field | Meaning |
|---|---|
| `config` | `config/shards/engine.toml`, shared by every shard: BM25 alone (`dense_weight = 0`) |
| `db_path`, `index_path` | where the engine places the shard's corpus database and its empty vectors database |
| `release_dir` | the shard's folder under the engine's data root |
| `label`, `blurb`, `jurisdiction_phrase` | display text, from the plan: the places and the years |
| `tier` | `INDEXED` until the shard's audit; `AI-AUDITED` (with `audit`) or `HUMAN-AUDITED` after it (`serve_shards.py tier`) |
| `[shard]` | `jurisdictions`, `first_year`, `last_year`, `undated` and `documents`, as in the plan |
| `[r2]` | `db_key` and `db_sha256` (from the builder's manifest), `index_key` and `index_sha256` (the empty vectors database) |

A shard is served by an engine Worker deployment only when the deployment's `SHARDS` variable names
it. Production starts with none. A shard is added there one at a time, after its audit and its smoke
tests pass on staging. Run `scripts/v2/export_worker_config.py` after any change. The Worker's
generated config marks each shard scope `shard: true` and carries its `tier`.

## Router index (`router/v1/` on R2)

Written by `scripts/v2/router_index.py build` from the coverage file of every shard in
`config/shards/served.toml`. The engine Worker reads it to choose which shard engines to wake for a
whole-collection question (`/ask?scope=collection`), without waking any.

| Key | Content |
|---|---|
| `router/v1/<digest>/df/<bucket>.tsv` | one line per term: `term<TAB>shard:df,shard:df,...`, for every term in two or more of a shard's passages |
| `router/v1/<digest>/complete` | written after the last bucket |
| `router/v1/shards.json` | the pointer, written last: `format`, `digest`, `prefix` (`router/v1/<digest>`), `buckets`, `built_at`, `N`, `tokens`, `avgdl`, and `shards`: for each shard its `jurisdictions`, `years`, `passages`, `tokens` and `tier` |

A term's bucket is FNV-1a (32 bit, over the term's UTF-8 bytes) modulo `buckets` (4096), written as
four digits. Terms are the coverage file's: lower-cased words (letters and numbers), the frozen
stopwords removed. The folder is named by a digest of its content, and the pointer moves last, so a
reader never sees a half-written index; earlier folders stay.

The Worker uses only the shards its deployment serves (`SHARDS`); N, the average length and the
document frequencies are summed over those. A served shard missing from the index is reported as
not searched ("not in the router index yet"). The Worker's settings (`max_engines`, `top_k`,
`pool_size`) come from `config/shards/router.toml`, exported into its generated config.

### The flow of one whole-collection question

1. The Worker reads the pointer and the buckets of the question's words, and chooses at most
   `max_engines` served shards. A shard is left out, with the reason, when its places or years cannot
   satisfy the filters, when none of the question's words occur in it, or when it ranks below the
   engines woken.
2. It asks each chosen engine for its record (`POST /ask?scope=<shard>` with `evidence_only` and the
   `x-civic-router: 1` header). For that header alone, the reply adds `router.hits`: the pool's rows
   with their text, date method, counts of the question's words (`tf`) and length (`dl`). The Worker
   sets the header itself and never forwards a visitor's headers, so a visitor never receives them.
3. It scores every candidate again with collection-wide BM25 and keeps `pool_size` of them.
4. It sends them to the first chosen engine's `POST /compose`, which makes the one writer call on the
   top `top_k` and checks each citation against exactly the rows sent. It returns the answer, the
   evidence (each row then marked with its `shard` and `tier`) and a `router` block that lists the
   shards searched and the shards left out, each with why. Not searched is never "not in the archive".

While a chosen engine wakes, the Worker answers 503 with each engine's state, as a single-scope
question does, and the site retries. Whole-collection answers are never stored.
