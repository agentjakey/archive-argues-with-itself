"""archive_debugger: a civic memory debugger for Canada's public record.

This package is organized into layers with strict boundaries. The boundaries
are the point of the project, not an afterthought:

    harvest/   network layer. The ONLY layer allowed to make outbound calls to
               the Internet Archive or anywhere else. Writes raw responses and
               OCR derivatives to local storage. Nothing downstream touches the
               network.

    ingest/    local layer. Parses harvested material, normalizes dates,
               issuing bodies, jurisdictions, item ids and page references, and
               builds the hybrid (lexical + vector) index. No network access.

    retrieve/  local read layer. Runs hybrid retrieval over the built index and
               returns page-level passages with provenance. No network access.

    generate/  synthesis layer. Produces answers ONLY from retrieved passages,
               with a page-level source on every claim. No network access to the
               archive; may call a configured LLM endpoint if and when that is
               wired up, and never invents citations or page numbers.

    eval/      evaluation layer. Scores retrieval quality and citation support
               against a hand-built question set. No network access.

    api/       serve layer. Read-only HTTP surface over the built index and
               retrieval. Never harvests, never writes to the index, never makes
               hidden network calls.

Nothing is implemented yet. This module exists to declare the contract.
"""

__version__ = "0.0.0"
