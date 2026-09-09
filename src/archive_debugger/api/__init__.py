"""api: the read-only serve layer.

Responsibility:
    Expose a read-only HTTP surface (FastAPI) over the built index and the
    retrieve layer, feeding the two linked views in web/: the evidence timeline
    and the coverage view.

Boundary rules:
    - Read only. Never harvests, never writes to civic.db, never re-fetches IA
      corpus data.
    - Serves provenance and coverage signals through to the client so the
      interface can show sources and gaps, not just answers.

Nothing is implemented yet.
"""
