"""The short link /kiosk opens the online exhibit in kiosk presentation (site/static/_redirects), and the
exhibit app reads ?kiosk=1 with counting and printing off (exhibit/app/src/lib/kiosk.ts)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_kiosk_short_link_redirects_to_the_exhibit_in_kiosk_mode():
    rules = [line.split() for line in (REPO / "site" / "static" / "_redirects").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert ["/kiosk", "/exhibit/?kiosk=1", "302"] in rules
    assert ["/kiosk/", "/exhibit/?kiosk=1", "302"] in rules


def test_kiosk_from_the_address_never_counts_or_prints():
    source = (REPO / "exhibit" / "app" / "src" / "lib" / "kiosk.ts").read_text(encoding="utf-8")
    assert 'get("kiosk") === "1" ? { kiosk: true, idle_reset_seconds: 60, printer: false, counting: false }' in source
    assert "!config.counting" in source
