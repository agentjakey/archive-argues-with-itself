"""Answer parity between v1 serving and Phase 1 serving, on the seed and story questions.

  capture   run the real retrieval for every seed and story question of a scope and write the
            ranked pool (passage ids, in order) and the prompt prefix for each. --layout v1 serves
            the dense leg the way v1 deployed it: numpy, the matrix built row by row from the full
            published vectors database. --layout artifacts serves it the Phase 1 way: numpy from
            the .npy artifacts, with the boot's small stand-in index in place of the vectors
            database. Each layout is built in a scratch folder of hard links to the verified files.
  compare   the two captures must be identical, question by question. Retrieval feeds every
            evaluation metric and every answer, so identical pools mean unchanged eval numbers and
            unchanged answers for these questions.
  answers   every stored answer migrated to the v2 cache is the v1 stored answer, unchanged: the
            text, sentences, verified citations, unsupported sentences, abstention and evidence.

    python scripts/v2/parity.py capture --scope pilot --layout v1 --src C:/civic-measure/src --out reports/v2/raw/parity_pilot_v1.json
    python scripts/v2/parity.py capture --scope pilot --layout artifacts --src C:/civic-measure/src --out reports/v2/raw/parity_pilot_artifacts.json
    python scripts/v2/parity.py compare reports/v2/raw/parity_pilot_v1.json reports/v2/raw/parity_pilot_artifacts.json
    python scripts/v2/parity.py answers --scope pilot --old data/cache/answers.db --new data/cache/answers.db
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path



def link(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)


def build_layout(scope: str, layout: str, src: Path, work: Path) -> tuple[Path, Path]:
    """A scratch copy of the scope's files (hard links): v1 = db + full index, no artifacts;
    artifacts = db + stand-in index + the three artifact files."""
    from archive_debugger import provision
    from archive_debugger.api.cache import canonical_data_sha256
    from archive_debugger.retrieve import dense
    from archive_debugger import release_files
    files = {f.kind: f for f in release_files.scope_files(scope)}
    db = work / Path(files["db"].relative).name
    index = work / "index" / Path(files["index"].relative).name
    link(files["db"].path(src), db)
    if layout == "v1":
        link(files["index"].path(src), index)
    else:
        provision.write_stub_index(index, canonical_data_sha256(scope)["index"])
        published = dense.artifact_paths(files["index"].path(src))
        local = dense.artifact_paths(index)
        for part in ("matrix", "ids", "manifest"):
            link(published[part], local[part])
    return db, index


def capture(scope: str, layout: str, src: Path, out: Path) -> int:
    from archive_debugger import scopes
    from archive_debugger.api.app import clean_question
    from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool
    from archive_debugger.retrieve.search import Retriever

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrate_cache import curated_questions

    os.environ["CIVIC_DENSE_BACKEND"] = "numpy"
    with tempfile.TemporaryDirectory(prefix=f"parity-{scope}-{layout}-", dir=src) as tmp:
        db, index = build_layout(scope, layout, src, Path(tmp))
        from archive_debugger import release_files
        db_env, index_env = release_files.path_env_names(scope)
        os.environ[db_env], os.environ[index_env] = str(db), str(index)
        resolved = scopes.resolve_scope(scope)
        active = None if resolved.inherit else resolved
        with scopes.activate(active):
            retriever = Retriever(Path(resolved.config_path))
            gcfg = load_generate_config(Path(resolved.config_path))
        if retriever.dense_index is None:
            print(f"{layout}: the resident dense index did not load", file=sys.stderr)
            return 1
        rows = {}
        for q in curated_questions(scope):
            pool, hits = retrieve_pool(retriever, clean_question(q["question"]), build_filters(q["filters"]), gcfg["top_k"])
            rows[q["label"]] = {"pool": [h["passage_id"] for h in pool], "prompt": [h["passage_id"] for h in hits]}
        retriever.close()
        source = "artifacts" if layout == "artifacts" else "rows"
        record = {"scope": scope, "layout": layout, "dense_source": source, "questions": rows,
                  "dense_rows": retriever.dense_index.n}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"{scope} {layout}: {len(rows)} questions captured ({retriever.dense_index.n} dense rows) -> {out}")
    return 0


def compare(a_path: Path, b_path: Path) -> int:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    differ = [label for label in sorted(set(a["questions"]) | set(b["questions"]))
              if a["questions"].get(label) != b["questions"].get(label)]
    print(json.dumps({"scope": a["scope"], "a": a["layout"], "b": b["layout"], "questions": len(a["questions"]),
                      "identical": len(a["questions"]) - len(differ), "differ": differ}))
    return 0 if not differ and a["questions"] else 1


def answers(scope: str, old_db: Path, new_db: Path) -> int:
    """The migrated v2 rows hold the v1 stored answers unchanged (curated rows only)."""
    from archive_debugger.api.app import scope_cache_context, answer_cache_key
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrate_cache import curated_questions

    fields = ("text", "sentences", "verified_citations", "unsupported", "abstained", "abstention_text", "generation")
    old = sqlite3.connect(f"file:{old_db.resolve().as_posix()}?mode=ro", uri=True)
    new = sqlite3.connect(f"file:{new_db.resolve().as_posix()}?mode=ro", uri=True)
    old_answers = {}
    for (body,) in old.execute("SELECT response_json FROM answers"):
        response = json.loads(body)
        signature = (response["answer"].get("text"), json.dumps(response["answer"].get("sentences"), sort_keys=True))
        old_answers.setdefault(signature, []).append(response)
    context = scope_cache_context(scope)
    checked, missing, changed = 0, [], []
    for q in curated_questions(scope):
        row = new.execute("SELECT response_json FROM answers_v2 WHERE key = ?",
                          (answer_cache_key(context, q["question"], q["filters"]),)).fetchone()
        if row is None:
            missing.append(q["label"])
            continue
        response = json.loads(row[0])
        signature = (response["answer"].get("text"), json.dumps(response["answer"].get("sentences"), sort_keys=True))
        checked += 1
        # Abstentions share their wording, so a stored answer is unchanged when any v1 row with the
        # same text matches it field for field and passage for passage.
        same = [before for before in old_answers.get(signature, [])
                if all(before["answer"].get(f) == response["answer"].get(f) for f in fields)
                and [e["passage_id"] for e in before["evidence"]] == [e["passage_id"] for e in response["evidence"]]]
        if not same:
            changed.append(q["label"])
    print(json.dumps({"scope": scope, "curated_rows_checked": checked, "unchanged": checked - len(changed),
                      "changed": changed, "not_in_v2_cache": missing}))
    return 0 if not changed else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--scope", required=True, help="a scope in config/scopes.toml")
    c.add_argument("--layout", choices=["v1", "artifacts"], required=True)
    c.add_argument("--src", type=Path, required=True, help="folder with the verified data and artifacts")
    c.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("compare")
    m.add_argument("a", type=Path)
    m.add_argument("b", type=Path)
    s = sub.add_parser("answers")
    s.add_argument("--scope", required=True, help="a scope in config/scopes.toml")
    s.add_argument("--old", type=Path, required=True)
    s.add_argument("--new", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "capture":
        return capture(args.scope, args.layout, args.src, args.out)
    if args.command == "compare":
        return compare(args.a, args.b)
    return answers(args.scope, args.old, args.new)


if __name__ == "__main__":
    sys.exit(main())
