"""Store every curated answer that costs nothing: the seed and story questions that the abstention
gate answers before any model call.

The app runs in this process against the local data and the local answer caches, with the model
pointed at an unroutable host, so no request can reach a paid API. A curated question that the
gate abstains on is stored like any served abstention (it is the system's real answer, made now).
A question that needs the model degrades to limited mode, which is never stored, and is listed as
needing a paid run. Prints the per-question outcome and totals; question text is curated and
public.

    CIVIC_DB_PATH=... CIVIC_INDEX_PATH=... python scripts/v2/warm_curated_free.py --scopes pilot,microlog
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ["ANTHROPIC_BASE_URL"] = "http://offline.invalid"   # before anything imports the SDK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scopes", default="", help="comma-separated scopes; default: every scope in config/scopes.toml")
    args = parser.parse_args(argv)
    from archive_debugger import release_files
    wanted = [s.strip() for s in args.scopes.split(",") if s.strip()] or release_files.scope_names()

    from fastapi.testclient import TestClient

    from archive_debugger.api.app import create_app

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrate_cache import curated_questions

    from archive_debugger import scopes as _scopes
    _default = _scopes.load_registry().get("default")
    _base_config = Path(_scopes.resolve_scope(_default).config_path)
    app = create_app(_base_config, load_env=True, serve_scopes=[s for s in wanted if s != _default])
    totals = {"already_stored": 0, "stored_abstention": 0, "needs_model": 0, "other": 0}
    rows = []
    with TestClient(app, raise_server_exceptions=False) as client:
        if not app.state.ready.wait(600):                  # the scopes open in the background
            print(f"server never became ready: {app.state.startup_error}")
            return 1
        for scope in wanted:
            if scope not in app.state.bundles:
                print(f"scope {scope} is not served here (no data); skipped")
                continue
            for q in curated_questions(scope):
                resp = client.post(f"/ask?scope={scope}", json={"question": q["question"], "filters": q["filters"]})
                body = resp.json() if resp.status_code == 200 else {}
                answer = body.get("answer") or {}
                if answer.get("cached"):
                    outcome = "already_stored"
                elif body.get("degraded"):
                    outcome = "needs_model"
                elif answer.get("abstained"):
                    outcome = "stored_abstention"
                else:
                    outcome = "other"
                totals[outcome] += 1
                rows.append({"scope": scope, "label": q["label"], "outcome": outcome})
    for row in rows:
        print(json.dumps(row))
    print(json.dumps(totals))
    return 0 if totals["other"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
