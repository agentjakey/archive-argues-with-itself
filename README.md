# archive-argues-with-itself

An open-source civic memory debugger for exploring how Canadian government
records change over time, with page-level provenance, temporal comparison, and
visible archival uncertainty.

This is an inspectable civic-memory tool, not a generic RAG chatbot. Retrieval,
provenance, coverage, and uncertainty matter more than answer fluency.

## Status

Scaffold. Structure is in place; no logic is implemented yet. See
`docs/PROPOSAL.md` for the source-of-truth scope.

## Principles

- Bounded pilot corpus, not the whole collection.
- Use existing Internet Archive OCR first.
- Page-level provenance on every claim.
- Hybrid retrieval (lexical + vector).
- Temporal comparison across years.
- Visible uncertainty and coverage gaps.
- Evaluation before demo polish.
- Open-source reproducibility.

## Architecture

Three separated concerns, with the network boundary as the load-bearing rule:

- `src/archive_debugger/harvest/` — network layer. The only layer that reaches
  the Internet Archive. Caches raw metadata and OCR under `raw/`.
- `src/archive_debugger/ingest/` — local parse, normalize, and index.
- `src/archive_debugger/retrieve/` — local hybrid retrieval over the index.
- `src/archive_debugger/generate/` — synthesis grounded strictly in retrieved
  passages.
- `src/archive_debugger/eval/` — retrieval and citation-support evaluation.
- `src/archive_debugger/api/` — read-only serve layer (FastAPI).
- `web/` — Next.js interface: evidence timeline and coverage views.

Nothing after harvest re-fetches Internet Archive corpus data; ingest, retrieve,
and serve run from `raw/` and `civic.db`. Generation may call an explicitly
configured external LLM API (isolated, config-driven; stubbed in CI).

## Layout

```
config/pilot.toml     pilot topic, window, and IA queries (values TODO)
docs/PROPOSAL.md      submitted proposal (source of truth for scope)
src/archive_debugger/ python layers (see Architecture)
web/                  Next.js read-only interface
tests/                pytest suite; tests/fixtures/ holds small real fixtures
Makefile              harvest / index / eval / serve targets
pyproject.toml        Python 3.11, pinned dependencies
```

## Quickstart

```
make install       # install the python package (dev extras)
make install-web   # install web/ node dependencies
make harvest       # collect IA metadata + OCR (network layer)
make index         # parse, normalize, build the hybrid index (local)
make eval          # run retrieval + citation-support evaluation (local)
make serve         # run the read-only api (local)
make web           # run the Next.js interface (dev)
```

Targets currently print a not-implemented notice; they will be wired up in
later phases.

## Reproducibility

Everything needed to rebuild the pilot is open source. The pilot corpus is
defined entirely by `config/pilot.toml`, and harvested material under `raw/` is
regenerated rather than committed.

## License

MIT. See `LICENSE`.
