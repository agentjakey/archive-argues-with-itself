"""retrieve: hybrid retrieval over the built index (local read only).

Responsibility:
    Given a civic question, return the most relevant page-level passages using
    hybrid retrieval (lexical and vector), each carrying its provenance and the
    coverage signals attached during ingest.

Boundary rules:
    - No network access. Reads only the local index built by ingest.
    - Every returned passage keeps its item id and page number.
    - Retrieval surfaces coverage context (date and jurisdiction distribution,
      sparsity) alongside results so downstream layers can show uncertainty.

Nothing is implemented yet.
"""
