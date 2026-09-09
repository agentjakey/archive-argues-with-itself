"""archive_debugger: a civic memory debugger for Canada's public record.

This package is organized into layers with strict boundaries. The boundaries
are the point of the project, not an afterthought:

    harvest/   network layer. The ONLY layer that ingests IA corpus data. Writes
               raw responses and OCR derivatives to raw/. Nothing downstream
               re-fetches IA corpus data; everything after harvest runs from raw/
               and civic.db.

    ingest/    local layer. Parses harvested material, normalizes dates,
               issuing bodies, jurisdictions, item ids and page references, and
               builds the hybrid (lexical + vector) index in civic.db. No IA
               corpus re-fetch.

    retrieve/  local read layer. Runs hybrid retrieval over civic.db and returns
               page-level passages with provenance. No IA corpus re-fetch.

    generate/  synthesis layer. Produces answers ONLY from retrieved passages,
               with a page-level source on every claim. No IA corpus re-fetch. May
               call an explicitly configured external LLM API (isolated,
               config-driven); CI tests stub the LLM and never call a real API.
               Never invents citations or page numbers.

    eval/      evaluation layer. Scores retrieval quality and citation support
               against a hand-built question set. No IA corpus re-fetch.

    api/       serve layer. Read-only HTTP surface over civic.db and retrieval.
               Never harvests, never writes to civic.db, never re-fetches IA
               corpus data.

Nothing is implemented yet. This module exists to declare the contract.
"""

__version__ = "0.0.0"
