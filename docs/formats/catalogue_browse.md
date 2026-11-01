# Catalogue browsing files

The site's `/catalogue/` page lists every document the project knows, by decade, place, issuer and
sub-collection, with its coverage state. It reads only static files compiled from the registry
(`scripts/v2/catalogue.py browse`, code `src/archive_debugger/catalogue/browse.py`), which a site
release publishes at `/catalogue/data/`.

## `summary.json`

| Field | Meaning |
|---|---|
| `documents` | how many documents are listed |
| `decades` | `{key: {documents, bytes, sha256}}` for every decade file. The key is `"1970s"` or `"undated"` |
| `grid` | `[{decade, place, documents}]` |
| `coverage` | how many documents have reached each state: `known`, `text_fetched`, `indexed` |
| `places`, `collections`, `issuers` | document counts. The page lists the 150 largest sub-collections and the 300 largest issuers |
| `source` | when and how the catalogue was fetched, in a sentence the page shows |

## `decades/<key>.json`

A list of documents, each with these fields:

| Field | Meaning |
|---|---|
| `id` | the archive.org identifier. The page links to `https://archive.org/details/<id>` |
| `t` | the title, cut at 240 characters |
| `y` | the catalogue's year, or `null` |
| `d` | `{year, method}` for a year read from the title when the catalogue has none, or `null`. It is shown as "read from the title", never as the catalogue's date |
| `p` | the place, read from the publisher or creator by the site's rules, or `unknown` |
| `i` | the issuer, or `null` |
| `c` | the sub-collections other than the source collection |
| `s` | the coverage states, for example `known`, `text_fetched` or `indexed:microlog` |

A site release's gate checks that each decade file matches the sha256 the summary gives for it, that
every row has an identifier and the `known` state, and that the row count equals the summary's.
