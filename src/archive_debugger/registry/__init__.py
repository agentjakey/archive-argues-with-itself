"""The normalized registry (docs/formats/registry.md): one SQLite file that knows every document in
every archive this project draws on, how it can be located, what may be done with it, which dates
it carries and how each was found, which text versions exist, which pages and passages are indexed,
its coverage state, any governance policy on it, and an append-only audit trail.

Identifiers are stable and readable: an archive is "ia"; a collection "ia:<collection>"; a document
"ia:<identifier>"; a page "ia:<identifier>#<leaf>"; a passage keeps the corpus's own id
"<identifier>#<leaf>:<n>", so every v1 citation and recorded answer still resolves, unchanged; a
text version "ia:<identifier>@<kind>:<sha12>". The registry is built from files (the catalogue, the
indexed corpora, the governance register, fetched text); it is never edited by hand."""
