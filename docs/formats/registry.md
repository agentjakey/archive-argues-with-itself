# Registry format

The registry is one SQLite file (`data/registry/registry.db`, rebuilt by `scripts/v2/registry.py`)
that lists every document this project knows. Schema: `src/archive_debugger/registry/schema.py`.
It is built from files and never edited by hand. Rebuilding it from the same files gives the same
rows.

## Identifiers

Identifiers are stable and readable.

| Thing | Identifier | Example |
|---|---|---|
| archive | `ia` | `ia` |
| collection | `ia:<collection>` | `ia:governmentpublications` |
| document | `ia:<archive.org identifier>` | `ia:31761049004518` |
| page | `ia:<identifier>#<leaf>` | `ia:31761049004518#2` |
| passage | the corpus's own `<identifier>#<leaf>:<n>`, unchanged, so every v1 citation still resolves | `31761049004518#2:0` |
| text version | `ia:<identifier>@<kind>:<sha12>` | `ia:31761049004518@djvu_txt:3fa0c19b22e1` |

A page's leaf is its position among the leaves the archive.org viewer shows, so
`https://archive.org/details/<identifier>/page/n<leaf>` opens it. It is not the scan number. The
OCR's page index counts every scan, including the colour cards the viewer skips.

## Tables

| Table | What it holds |
|---|---|
| `archives`, `collections` | where documents come from. A collection's `role` is `source` (fetched whole) or `membership` (named by a record) |
| `documents` | the catalogue fields as fetched (title, creator, publisher, language, scanned pages), with the issuer and place normalized by the site's rules and how each was found, and the record's sha256 |
| `document_collections` | every collection each document belongs to |
| `licences` | the licence URL and rights statement as the catalogue gives them, and what the project may do: "catalogue terms only: not reviewed for reuse" until reviewed |
| `dates` | one row per kind: `catalogue` (the record's date field, with its parse method), `derived` (a year read from the title or the page, with the evidence), `capture` (web captures), `added` (when the archive added it). A derived date never overwrites the catalogue's |
| `versions` | each copy of a document's text: `corpus` (an indexed corpus), `djvu_txt` or the hOCR search text (a full-text fetch: source URL, store key, sha256, size, whether it can be cut by page), `reocr:<engine>` (a new OCR reading) |
| `pages`, `passages` | the indexed pages and passages, with the text's sha256 and the engine scope that serves each one |
| `locators` | the URLs that open a document or page: details page, viewer page, page image, text file |
| `coverage` | the states a document has reached: `known`, `text_fetched`, `indexed` (with the scope), `verified`, `absent`. "Not indexed" is never reported as "not in the archive" |
| `governance` | the governance register's production policies, for each document they target (docs/formats/governance.md). A fixture policy is refused |
| `audit_trail` | one row per build step: when, which script and version, what was added. The database refuses updates and deletes on this table |
