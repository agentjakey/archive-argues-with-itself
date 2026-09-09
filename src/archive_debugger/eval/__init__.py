"""eval: retrieval and citation-support evaluation (local only).

Responsibility:
    Score the pipeline against a hand-built set of civic questions before any
    demo polish. Measures retrieval quality and citation support, and records
    failure cases honestly.

Boundary rules:
    - No network access. Operates over the local index and stored gold data.
    - Gold data and criteria are never silently relabeled or weakened to improve
      a number. A regression is reported, not hidden.
    - Metrics are computed from real runs, never placeholder or synthetic values.

Nothing is implemented yet.
"""
