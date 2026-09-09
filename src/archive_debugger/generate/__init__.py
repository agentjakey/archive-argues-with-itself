"""generate: synthesis grounded strictly in retrieved passages.

Responsibility:
    Compose an answer only from passages returned by retrieve, attaching a
    page-level source to every claim. Weakly supported or undated material stays
    visibly uncertain rather than being smoothed into a confident answer.

Boundary rules:
    - No IA corpus re-fetch. May call an explicitly configured external LLM API,
      kept isolated and config-driven. CI stays hermetic: generation tests use a
      stubbed LLM and never make a real API call.
    - Never fabricates citations, page numbers, dates, or quotations.
    - A claim without a retrieved source is not emitted as supported.
    - This layer is downstream of retrieve and never reads civic.db directly.

Nothing is implemented yet.
"""
