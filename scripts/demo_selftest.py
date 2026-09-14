"""Pre-doors ship gate: one command that runs the three offline checks in order and
prints a single combined GREEN or RED.

It runs, in sequence:
  1. scripts/preflight.py           -- needs the API running; proves the data files,
                                       the warmed answer cache, the page pack, and the
                                       offline retrieval stack are all real and present.
  2. scripts/scan_coverage.py       -- needs the answer cache and the page pack; no API.
                                       Every citation the exhibit can surface has a scan.
  3. scripts/offline_walkthrough.py -- forces the model offline in-process; no API, no
                                       pack; proves the request path degrades cleanly.

Each sub-check prints its own green/red lines; this wrapper repeats each one's verdict,
prints one combined result, and exits non-zero if any sub-check is red. Nothing here
writes to the corpus, the answer cache, or any published number (N5); it only runs the
three read-only checks.

Prerequisites for an all-GREEN result (see docs/RUNBOOK.md):
  - the API is running (python -m uvicorn archive_debugger.api.app:app --port 8000);
  - the Wi-Fi is off (a true offline test); and
  - the offline page pack is built (scripts/offline_pack.py). Without the pack,
    preflight and scan_coverage are RED on the missing page images by design, and this
    wrapper names the pack as the cause.

    python scripts/demo_selftest.py
    python scripts/demo_selftest.py http://127.0.0.1:8000
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Substrings that mark a failure as "the page pack is not built" rather than something
# else. preflight prints the page-images check; scan_coverage prints the render line.
PACK_SIGNALS = ("page images", "cannot render offline", "run scripts/offline_pack.py",
                "Extend the pack")


def checks(base: str) -> list[tuple[str, list[str]]]:
    """(label, argv) for each sub-check, in run order. Only preflight takes the API base."""
    py = sys.executable
    return [
        ("preflight        (API up: data, cache, page pack, offline retrieval)",
         [py, "scripts/preflight.py", base]),
        ("scan_coverage    (page pack covers every surfaceable citation)",
         [py, "scripts/scan_coverage.py"]),
        ("offline_walkthrough (request path degrades cleanly, model offline)",
         [py, "scripts/offline_walkthrough.py"]),
    ]


def verdict_line(output: str) -> str:
    """The sub-check's own final GREEN/RED summary line, or the last non-empty line."""
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("GREEN:") or ln.startswith("RED:"):
            return ln
    return lines[-1] if lines else "(no output)"


def run_check(argv: list[str]) -> tuple[bool, str, str]:
    """Run one sub-check as a subprocess. Returns (passed, verdict_line, full_output)."""
    proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr.strip():
        output = output + "\n" + proc.stderr
    return proc.returncode == 0, verdict_line(output), output


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    base = args[0] if args else "http://127.0.0.1:8000"

    print("Demo self-test: the pre-doors ship gate.")
    print("Prerequisites for GREEN: API running, Wi-Fi off, offline page pack built.")
    print(f"preflight target: {base}")
    print("=" * 72)

    results = []
    non_pack_failure = False
    for label, cmd in checks(base):
        print(f"\n>>> {label}")
        ok, verdict, output = run_check(cmd)
        print(f"    {'GREEN' if ok else 'RED  '}  {verdict}")
        results.append((label, ok))
        if not ok and not any(sig in output for sig in PACK_SIGNALS):
            non_pack_failure = True

    reds = [label for label, ok in results if not ok]
    print("\n" + "=" * 72)
    for label, ok in results:
        print(f"  [{'GREEN' if ok else ' RED '}] {label}")
    print()

    if not reds:
        print("DEMO SELF-TEST: GREEN. Every offline check passed. Clear to open the doors.")
        return 0

    print(f"DEMO SELF-TEST: RED. {len(reds)} of {len(results)} sub-check(s) failed.")
    if not non_pack_failure:
        print("Cause: the offline page pack is not built (data/cache/pages). This is the")
        print("expected state on a fresh machine and the only thing standing between this")
        print("box and GREEN. Build it once with the network on, then re-run:")
        print("  python scripts/warm_cache.py http://127.0.0.1:8000")
        print("  python scripts/offline_pack.py --contact you@example.com")
        print("  python scripts/scan_coverage.py        # repeat until GREEN")
        print("See docs/RUNBOOK.md, 'Build the page pack (network on, once)'.")
    else:
        print("At least one failure is NOT the page pack (the API may be down, or a data")
        print("file or the retrieval stack is missing). Read the sub-check output above and")
        print("docs/RUNBOOK.md, 'What GREEN means and what to do on each RED', before doors.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
