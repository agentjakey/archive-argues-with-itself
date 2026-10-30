"""Regenerate the kiosk QR code (web/src/components/KioskQr.tsx) for the site's canonical URL.

The component holds the QR as a static SVG path, so it needs no runtime library and works offline.
This rewrites QR_SIZE and QR_PATH in place from a fresh segno matrix (error correction M, a
four-module quiet zone). Needs segno (pip install segno --break-system-packages).

    python scripts/v2/make_qr.py https://archiveargues.org
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

COMPONENT = Path("web/src/components/KioskQr.tsx")
BORDER = 4


def qr_path(url: str) -> tuple[int, str]:
    import segno
    matrix = segno.make(url, error="m").matrix
    path = "".join(f"M{c + BORDER} {r + BORDER}h1v1h-1z"
                   for r, row in enumerate(matrix) for c, value in enumerate(row) if value)
    return len(matrix) + 2 * BORDER, path


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not args[0].startswith("https://"):
        print("usage: python scripts/v2/make_qr.py https://<site>", file=sys.stderr)
        return 2
    size, path = qr_path(args[0])
    text = COMPONENT.read_text(encoding="utf-8")
    text, n_size = re.subn(r"const QR_SIZE = \d+;", f"const QR_SIZE = {size};", text)
    text, n_path = re.subn(r'const QR_PATH =\n  "[^"]*";', f'const QR_PATH =\n  "{path}";', text)
    if n_size != 1 or n_path != 1:
        print(f"{COMPONENT}: could not find QR_SIZE and QR_PATH to replace", file=sys.stderr)
        return 1
    COMPONENT.write_text(text, encoding="utf-8")
    print(f"QR for {args[0]}: {size} modules, written to {COMPONENT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
