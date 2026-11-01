"""Print the engine's wake log from GET /health?wakes=1 and flag every wake that did not end in
"slept: idle". Standard library only; reads /health, which never wakes the engine.

    python scripts/v2/check_wakes.py
    python scripts/v2/check_wakes.py --site https://archiveargues.org
    python scripts/v2/check_wakes.py --api https://archive-argues-engine-staging.<sub>.workers.dev

A wake that is still running (no exit yet) is listed as open, not flagged. A trusted snapshot
restore whose background check failed is flagged by its exit. With --site, the site's home page
must answer 200 too. Exit status 1 when anything is flagged, 2 when the site or /health is down, so
the command can gate a script (the daily GitHub check fails on either).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_API = "https://api.archiveargues.org"
USER_AGENT = "archive-argues-check-wakes/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
CLEAN_EXIT = "slept: idle"


def fetch_health(api: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(f"{api.rstrip('/')}/health?wakes=1", headers={"user-agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def site_status(url: str, timeout: float = 30.0) -> int:
    """The HTTP status of a GET of the site's home page (0 when it could not be reached)."""
    req = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def seconds(value) -> str:
    return "-" if value is None else f"{value:.1f}s"


def review(health: dict) -> tuple[list[str], int]:
    """The report lines for a /health?wakes=1 body, and how many wakes were flagged."""
    lines = [f"release {health.get('release')}, status {health.get('status')}"]
    for engine in health.get("engines") or []:
        lines.append(f"  engine {engine.get('name')}: {engine.get('status')}"
                     + (f", error: {engine['error']}" if engine.get("error") else ""))
    wakes = sorted(health.get("wakes") or [], key=lambda w: w.get("started_at") or "")
    flagged = 0
    lines.append(f"{len(wakes)} wakes")
    for wake in wakes:
        exit_reason = wake.get("exit")
        if exit_reason is None:
            mark = "OPEN"
        elif exit_reason == CLEAN_EXIT:
            mark = "ok"
        else:
            mark = "FLAG"
            flagged += 1
        check = wake.get("snapshot_check")
        lines.append(
            f"  {mark:4}  {wake.get('started_at')}  {str(wake.get('name')):8}  {str(wake.get('mode')):16}  "
            f"release {wake.get('release')}  port {seconds(wake.get('port_open_seconds'))}  "
            f"ready {seconds(wake.get('ready_seconds'))}"
            + (f"  snapshot check {check}" if check else "")
            + f"  exit: {exit_reason if exit_reason is not None else '(still running)'}")
    lines.append(f"{flagged} flagged" if flagged else "nothing flagged: every finished wake ended in \"slept: idle\"")
    return lines, flagged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default=DEFAULT_API, help=f"engine Worker origin (default {DEFAULT_API})")
    parser.add_argument("--site", default=None, help="also require this site's home page to answer 200")
    args = parser.parse_args(argv)
    down = []
    if args.site:
        status = site_status(args.site)
        print(f"site {args.site}: {status or 'unreachable'}")
        if status != 200:
            down.append(f"site answered {status or 'nothing'}")
    try:
        health = fetch_health(args.api)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        down.append(f"/health failed: {exc}")
        health = None
    flagged = 0
    if health is not None:
        lines, flagged = review(health)
        print("\n".join(lines))
    if down:
        print("DOWN: " + "; ".join(down))
        return 2
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
