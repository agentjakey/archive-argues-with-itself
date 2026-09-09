"""ingest: parse, normalize, and index (local only).

Responsibility:
    Turn harvested raw material into a queryable, inspectable index. This
    includes parsing OCR page text, normalizing dates, issuing bodies,
    jurisdictions, item ids and page references, recording where those fields
    are missing or low-confidence, and building the hybrid lexical + vector
    index.

Boundary rules:
    - No network access. Reads only from local raw/ storage produced by harvest.
    - Missing or weak metadata (undated items, unknown jurisdiction, poor OCR)
      is recorded as an explicit signal, never silently dropped or guessed.
    - Provenance (item id, page number) is preserved on every indexed passage.

Nothing is implemented yet.
"""
