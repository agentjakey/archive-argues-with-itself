"""Write the engine Worker's generated config, worker/engine/src/generated/engine_config.json.

Everything the Worker needs to serve a stored answer without waking the engine, computed by the
engine's own code so the two cannot drift:
  - each scope's cache context for its configured provider and model (api/app.py
    scope_cache_context), and the engine's EXTRAS_VERSION;
  - the stopword list salient_terms() uses (frozen archive_debugger.stopwords);
  - the dated editorial notes about stored answers (config/editorial_notes.json);
  - the R2 object keys a container may read through the Worker (config/scopes.toml).

Run it whenever the scopes, the generation config, the prompt, the notes, or the code behind
EXTRAS_VERSION change; the release gate (scripts/v2/build_release.py) fails when the committed file
differs from a fresh export.

    python scripts/v2/export_worker_config.py [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

OUT = Path("worker/engine/src/generated/engine_config.json")


def build() -> dict:
    if os.environ.get("CIVIC_EMBEDDER"):
        raise SystemExit("unset CIVIC_EMBEDDER: the exported contexts must match the production embedder")
    from archive_debugger import editorial, release_files, scopes
    from archive_debugger.api import cache as answer_cache
    from archive_debugger.api.app import EXTRAS_VERSION, scope_cache_context
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger.stopwords import STOPWORDS

    registry = scopes.load_registry()
    scope_rows = {}
    for name in release_files.scope_names(registry):
        resolved = scopes.resolve_scope(name)
        gcfg = load_generate_config(Path(resolved.config_path))
        scope_rows[name] = {"context": scope_cache_context(name, registry=registry),
                            "provider": gcfg["provider"], "model": gcfg["model"]}
    keys = [f.key for f in release_files.all_files(registry)]
    notes = editorial.load_notes(editorial.DEFAULT_NOTES)
    answer_notes = []
    for n in notes["notes"]:
        target = n["target"]
        if target["kind"] != "answer":
            continue
        public = editorial._public(n)
        public["target"] = {"scope": target["scope"], "question": target["question"],
                            "cached_only": bool(target.get("cached_only"))}
        answer_notes.append(public)
    return {
        "generated_by": "scripts/v2/export_worker_config.py",
        "key_version": answer_cache.KEY_VERSION,
        "retention_days": answer_cache.RETENTION_DAYS,
        "extras_version": EXTRAS_VERSION,
        "default_scope": registry.get("default", "pilot"),
        "scopes": scope_rows,
        "stopwords": sorted(STOPWORDS),
        "answer_notes": answer_notes,
        "r2_keys": sorted(keys),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed file is out of date")
    args = parser.parse_args(argv)
    text = json.dumps(build(), indent=1, ensure_ascii=True, sort_keys=True) + "\n"
    if args.check:
        current = OUT.read_text(encoding="ascii") if OUT.exists() else ""
        if current != text:
            print(f"{OUT} is out of date: run python scripts/v2/export_worker_config.py", file=sys.stderr)
            return 1
        print(f"{OUT} is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="ascii")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
