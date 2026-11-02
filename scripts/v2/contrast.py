"""WCAG 2.2 contrast ratios for the colour tokens in design/tokens.css, checked against the bar each role has.

    python scripts/v2/contrast.py            # prints the table, exits 1 when a pair misses its bar

Roles: body text needs 7:1 (AAA); secondary text, links and labels 7:1 as well (they carry reading);
large text and the comparison colours 4.5:1 (AA); control edges 3:1 (non-text, 1.4.11). Each foreground
is measured on the ground and on both surfaces. Print colours (black on white) are checked too."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOKENS = REPO / "design" / "tokens.css"

# (token, bar, what it is for)
ROLES = [
    ("text", 7.0, "body text (AAA)"),
    ("muted", 7.0, "secondary text (AAA)"),
    ("gold", 7.0, "links, focus, hover, cited mark (AAA; never reading text on surface-2)"),
    ("split-a", 4.5, "first record of a comparison (AA)"),
    ("split-b", 4.5, "second record of a comparison (AA)"),
    ("accent", 4.5, "Agora accent: large text and rules only (AA)"),
    ("line", 3.0, "control edges (non-text, 3:1)"),
]
GROUNDS = ("bg", "surface", "surface-2")


def tokens(path: Path = TOKENS) -> dict:
    text = path.read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", text)}


def luminance(hex_colour: str) -> float:
    channels = []
    for i in (1, 3, 5):
        c = int(hex_colour[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main() -> int:
    t = tokens()
    misses = 0
    print("| Token | Use | Bar | " + " | ".join(f"on {g}" for g in GROUNDS) + " |")
    print("| --- | --- | --- |" + " --- |" * len(GROUNDS))
    for name, bar, use in ROLES:
        cells = []
        for g in GROUNDS:
            r = ratio(t[name], t[g])
            # Gold on surface-2 is used only for large text and focus rings (the exhibit), so AA applies there.
            need = 4.5 if (name == "gold" and g == "surface-2") else bar
            ok = r >= need
            misses += 0 if ok else 1
            cells.append(f"{r:.1f}{'' if ok else ' MISS'}{' (AA: large text only)' if need != bar else ''}")
        print(f"| {name} {t[name]} | {use} | {bar}:1 | " + " | ".join(cells) + " |")
    print(f"| ink on gold | text on a gold fill | 7.0:1 | {ratio(t['ink'], t['gold']):.1f} | | |")
    misses += 0 if ratio(t["ink"], t["gold"]) >= 7.0 else 1
    print(f"| print | black on white | 7.0:1 | {ratio('#000000', '#ffffff'):.1f} | | |")
    print(f"{misses} pair(s) below their bar")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
