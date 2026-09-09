"""generate: synthesis grounded strictly in retrieved passages.

Responsibility:
    Compose an answer only from passages returned by retrieve, attaching a
    page-level source to every claim. Weakly supported or undated material stays
    visibly uncertain rather than being smoothed into a confident answer.

Boundary rules:
    - No access to the Internet Archive. May call a configured LLM endpoint if
      one is wired up, but never fabricates citations, page numbers, dates, or
      quotations.
    - A claim without a retrieved source is not emitted as supported.
    - This layer is downstream of retrieve and never reads the index directly.

Nothing is implemented yet.
"""
