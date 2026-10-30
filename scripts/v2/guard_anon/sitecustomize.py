"""Measurement-only override of the dense memory guard, loaded by putting this directory on the
server's PYTHONPATH (scripts/v2/measure_boot.py --guard anon).

The serving guard (archive_debugger.retrieve.dense) adds the resident index size to the process
VmRSS and refuses the load above 90% of the container limit. VmRSS counts every page of the
SQLite files the connections memory-map, and those pages are page cache the kernel can reclaim,
so under a smaller limit the guard refuses a matrix that would fit. This override makes the guard
count RssAnon instead (memory the process owns and the kernel cannot drop), which is the design
proposed for Phase 1. It changes nothing else: the same estimate, the same 90% threshold, the same
fallback. It is never installed in the serving image.
"""
from __future__ import annotations

from typing import Optional


def _rss_anon() -> Optional[int]:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("RssAnon:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


try:
    from archive_debugger.retrieve import dense as _dense
    _dense._rss = _rss_anon
    print("[measure] dense guard counts RssAnon (measurement override)", flush=True)
except Exception as exc:  # noqa: BLE001 - a failed override must show in the log, not stop the server
    print(f"[measure] dense guard override not installed: {type(exc).__name__}: {exc}", flush=True)
