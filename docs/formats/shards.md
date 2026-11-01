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
