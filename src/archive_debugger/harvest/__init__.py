"""harvest: the network layer.

Responsibility:
    Collect Internet Archive metadata and existing OCR derivatives for the
    bounded pilot corpus defined in config/pilot.toml, and cache them locally
    under raw/ (which is not committed). This is the only layer permitted to
    reach the network.

Boundary rules:
    - All outbound requests to the Internet Archive live here.
    - Respect Internet Archive automated-access guidelines: identify the client,
      cache aggressively, back off, and never re-fetch what is already cached.
    - Prefer existing OCR derivatives over re-deriving text.
    - Downstream layers read only from local storage, never from this layer's
      live connections.

Nothing is implemented yet.
"""
