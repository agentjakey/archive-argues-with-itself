"""Build web/public/canada.geojson from Natural Earth 1:50m admin-1 (public domain).

NETWORK-ON, operator-run once; NOT run in-session (N1). Downloads Natural Earth admin-1, keeps
Canada's 13 provinces and territories, and simplifies with mapshaper to a small file (target
< ~150 KB) whose features are keyed by ISO 3166-2 code (e.g. CA-ON), which the coverage map matches
to each jurisdiction. If web/public/canada.geojson is absent the coverage map falls back to a text
list without erroring, so running this is optional but recommended for the exhibit.

Prereq: mapshaper (npm install -g mapshaper, or npx fetches it on first run). Then:

    python scripts/build_canada_map.py
    # or, with this repo's venv:
    .venv/Scripts/python.exe scripts/build_canada_map.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
          "geojson/ne_50m_admin_1_states_provinces.geojson")
OUT = Path("web/public/canada.geojson")


def canada_code(props: dict) -> str:
    """The feature's ISO 3166-2 code (e.g. CA-ON); fall back to CA-<postal>, then name."""
    code = props.get("iso_3166_2")
    if code:
        return code
    postal = props.get("postal")
    return f"CA-{postal}" if postal else (props.get("name") or "")


def main() -> int:
    print(f"downloading {NE_URL} ...")
    with urllib.request.urlopen(NE_URL, timeout=120) as fh:
        data = json.loads(fh.read().decode("utf-8"))
    feats = [f for f in data.get("features", [])
             if (f.get("properties") or {}).get("admin") == "Canada"
             or (f.get("properties") or {}).get("iso_a2") == "CA"]
    # Keep only the ISO 3166-2 code, dropping every other (and possibly non-ASCII) property, so the
    # shipped asset stays small and ASCII; the map maps CA-XX -> province name locally.
    out_feats = [{"type": "Feature", "properties": {"code": canada_code(f.get("properties") or {})},
                  "geometry": f.get("geometry")} for f in feats]
    print(f"Canada features: {len(out_feats)} (expected 13)")
    if len(out_feats) < 13:
        print("WARN: fewer than 13 features; check the Natural Earth 'admin'/'iso_a2' fields")

    tmp = Path(tempfile.gettempdir()) / "canada_raw.geojson"
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": out_feats}), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["npx", "mapshaper", str(tmp),
           "-simplify", "8%", "keep-shapes", "-clean",
           "-o", "format=geojson", "precision=0.01", str(OUT)]
    print("simplifying:", " ".join(cmd))
    subprocess.run(cmd, check=True, shell=(sys.platform == "win32"))

    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT} ({kb:.0f} KB, {len(out_feats)} features)")
    if kb > 150:
        print("NOTE: larger than the ~150 KB target; raise -simplify (e.g. 5%) to shrink further")
    return 0


if __name__ == "__main__":
    sys.exit(main())
