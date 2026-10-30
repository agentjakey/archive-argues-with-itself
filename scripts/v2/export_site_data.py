"""Compile the static site's data shards from the engine itself (format: docs/v2/formats/site_data.md).

Compile, don't query: everything the site shows that does not depend on a visitor's own question
is computed here, once, and published as versioned files: each scope's facts, seed examples,
stories (with their pinned pages, comparability blocks, dated notes and care flags), and the
recorded answer and coverage for every seed and story question that has a stored answer.

The engine runs in this process on the local data, read-only: the model is pointed at an
unroutable host and every cache write is intercepted, so nothing is generated or stored. A curated
question without a stored answer is listed in the index as missing (the release gate decides
whether that may ship). Only curated questions are exported; visitor rows are never read.

The data must be the published files (the release gate checks the scope hashes recorded here
against config/scopes.toml). Point the engine at the verified copies:

    CIVIC_DB_PATH=... CIVIC_INDEX_PATH=... python scripts/v2/export_site_data.py --out site/data
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlencode

os.environ["ANTHROPIC_BASE_URL"] = "http://offline.invalid"     # before anything imports the SDK
os.environ.pop("ANTHROPIC_API_KEY", None)                       # and no key: nothing can be generated

FORMAT_VERSION = 1
HEALTH_FIELDS = ("provider", "model", "corpus")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=None, separators=(",", ":"), sort_keys=True) + "\n",
                    encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="site/data", type=Path)
    parser.add_argument("--scopes", default="pilot,microlog")
    args = parser.parse_args(argv)
    wanted = [s.strip() for s in args.scopes.split(",") if s.strip()]

    from fastapi.testclient import TestClient

    from archive_debugger.api import cache as answer_cache
    from archive_debugger.api.app import create_app
    os.environ.pop("ANTHROPIC_API_KEY", None)     # importing the app module loads .env; remove the key again

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrate_cache import curated_questions

    if args.out.exists():
        shutil.rmtree(args.out)
    app = create_app(Path("config/pilot.toml"), load_env=False, serve_scopes=[s for s in wanted if s != "pilot"],
                     enabled_scopes=wanted)
    summary = {}
    with TestClient(app, raise_server_exceptions=False) as client:
        if not app.state.ready.wait(900):
            print(f"engine never became ready: {app.state.startup_error}", file=sys.stderr)
            return 1
        for bundle in app.state.bundles.values():                  # read-only: no cache writes
            bundle.cache.put = lambda record: record["created_at"]  # type: ignore[assignment]
        scopes_view = client.get("/scopes").json()
        scopes_view["scopes"] = [s for s in scopes_view["scopes"] if s["name"] in wanted]
        write_json(args.out / "scopes.json", scopes_view)
        write_json(args.out / "editorial_notes.json", client.get("/editorial-notes").json())
        for scope in wanted:
            if scope not in app.state.bundles:
                print(f"scope {scope} is not served here (no data); not exported", file=sys.stderr)
                return 1
            base = args.out / scope
            health = client.get(f"/health?scope={scope}").json()
            write_json(base / "health.json", {k: health[k] for k in HEALTH_FIELDS})
            write_json(base / "examples.json", client.get(f"/examples?scope={scope}").json())
            write_json(base / "stories.json", client.get(f"/stories?scope={scope}").json())
            index, missing = [], []
            for q in curated_questions(scope):
                slug = q["label"].replace(":", "-")
                resp = client.post(f"/ask?scope={scope}", json={"question": q["question"], "filters": q["filters"]}).json()
                entry = {"label": q["label"], "question": q["question"],
                         "normalized_question": answer_cache.normalize_question(q["question"]),
                         "filters": answer_cache.canonical_filters(q["filters"])}
                if not (resp.get("answer") or {}).get("cached"):
                    missing.append(q["label"])
                    index.append({**entry, "file": None})
                    continue
                write_json(base / "answers" / f"{slug}.json", resp)
                params = {"q": q["question"], "scope": scope, **{k: v for k, v in (q["filters"] or {}).items() if v}}
                cov = client.get(f"/coverage?{urlencode(params)}")
                if cov.status_code == 200:
                    write_json(base / "coverage" / f"{slug}.json", cov.json())
                index.append({**entry, "file": f"answers/{slug}.json",
                              "coverage": f"coverage/{slug}.json" if cov.status_code == 200 else None})
            write_json(base / "answers" / "index.json", {"format_version": FORMAT_VERSION, "scope": scope,
                                                         "data_sha256": answer_cache.canonical_data_sha256(scope),
                                                         "answers": index})
            summary[scope] = {"recorded": len(index) - len(missing), "missing": missing}
    write_json(args.out / "export.json", {"format_version": FORMAT_VERSION, "scopes": summary})
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
