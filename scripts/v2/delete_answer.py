"""Find the stored answer for a deletion request and print the command that deletes it.

A visitor's stored answer keeps no question text, only a key made from the question (format v2,
docs/formats/answer_cache.md). Given the question someone sends to hello@archiveargues.org, this
computes its key in every served collection, for the question as written and with no filters, and
prints the D1 command that deletes those rows (visitor rows only: curated rows are never touched).
It changes nothing itself; the account owner runs the printed command.

    python scripts/v2/delete_answer.py --question "the visitor's question"
    python scripts/v2/delete_answer.py --question "..." --filters '{"period": "1970s"}' --scope pilot
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

DATABASE = "archive-argues-cache"


def keys_for(question: str, filters: dict | None, scope_names: list[str]) -> dict[str, str]:
    from archive_debugger.api.app import answer_cache_key, scope_cache_context
    return {name: answer_cache_key(scope_cache_context(name), question, filters) for name in scope_names}


def delete_command(keys: list[str], env: str) -> str:
    listed = ", ".join(f"'{k}'" for k in keys)
    sql = f"DELETE FROM answers_v2 WHERE curated = 0 AND key IN ({listed})"
    return f'npx wrangler d1 execute {DATABASE} --remote --env {env} --command "{sql}"'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--question", required=True)
    parser.add_argument("--filters", default="", help="JSON object of filters, when the request names them")
    parser.add_argument("--scope", action="append", help="a collection name; default: every served collection")
    parser.add_argument("--env", default="production", choices=["production", "staging"])
    args = parser.parse_args(argv)
    filters = json.loads(args.filters) if args.filters else None
    if args.scope:
        names = args.scope
    else:
        config = json.loads((REPO / "worker" / "engine" / "src" / "generated" / "engine_config.json").read_text(encoding="utf-8"))
        names = sorted(config["scopes"])
    keys = keys_for(args.question, filters, names)
    for name, key in keys.items():
        print(f"{name}: {key}")
    print()
    print("Run from worker/engine (it deletes only visitor rows with these keys; 0 changes means none was stored):")
    print(delete_command(sorted(set(keys.values())), args.env))
    return 0


if __name__ == "__main__":
    sys.exit(main())
