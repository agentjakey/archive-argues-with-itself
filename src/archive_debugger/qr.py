"""QR codes as one SVG path (a module per square), so a page can draw them with no library and no
network. Used for the site's kiosk QR (scripts/v2/make_qr.py) and the exhibit's evidence cards.
Needs segno (BSD), a build-time tool only."""
from __future__ import annotations

BORDER = 4     # quiet zone, in modules


def qr_path(url: str) -> tuple:
    """(size in modules including the quiet zone, SVG path data) for url at error correction M."""
    import segno
    matrix = segno.make(url, error="m").matrix
    path = "".join(f"M{c + BORDER} {r + BORDER}h1v1h-1z"
                   for r, row in enumerate(matrix) for c, value in enumerate(row) if value)
    return len(matrix) + 2 * BORDER, path
