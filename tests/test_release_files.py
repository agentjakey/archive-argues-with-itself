"""A new collection is config plus data: its release files, their places on disk, the boot's plan
and the Worker's allow list all follow from its registry entry, with no code naming it."""
from __future__ import annotations

import hashlib

from archive_debugger import provision, release_files


def _registry() -> dict:
    h = lambda text: hashlib.sha256(text.encode()).hexdigest()   # noqa: E731
    return {"default": "pilot", "scopes": {
        "pilot": {"inherit": True, "config": "config/pilot.toml", "release_dir": "",
                  "r2": {"db_key": "pilot/civic.db", "db_sha256": h("a"), "index_key": "pilot/vectors.db",
                         "index_sha256": h("b")}},
        "ontario-reports": {"config": "config/pilot.toml", "release_dir": "ontario-reports",
                            "seed": "config/seed_questions.ontario.jsonl", "stories": "config/stories.ontario.json",
                            "r2": {"db_key": "ontario-reports/ontario.db", "db_sha256": h("c"),
                                   "index_key": "ontario-reports/vectors_ontario.db", "index_sha256": h("d")},
                            "dense": {"matrix_key": "ontario-reports/dense/vectors_ontario.matrix.npy", "matrix_sha256": h("e"),
                                      "ids_key": "ontario-reports/dense/vectors_ontario.ids.npy", "ids_sha256": h("f"),
                                      "manifest_key": "ontario-reports/dense/vectors_ontario.dense.json",
                                      "manifest_sha256": h("g")},
                            "facts": {"key": "ontario-reports/ontario.facts.json", "sha256": h("i")}},
    }}


def test_a_new_scope_is_laid_out_from_its_registry_entry():
    files = {f.kind: f for f in release_files.scope_files("ontario-reports", _registry())}
    assert files["db"].relative == "ontario-reports/ontario.db"
    assert files["index"].relative == "ontario-reports/index/vectors_ontario.db"
    assert files["dense_matrix"].relative == "ontario-reports/index/dense/vectors_ontario.matrix.npy"
    assert files["facts"].relative == "ontario-reports/ontario.facts.json"
    assert len(release_files.all_files(_registry())) == 2 + 6
    assert release_files.path_env_names("ontario-reports", _registry()) == ("ONTARIO_REPORTS_DB_PATH",
                                                                           "ONTARIO_REPORTS_INDEX_PATH")
    assert release_files.path_env_names("pilot", _registry()) == ("CIVIC_DB_PATH", "CIVIC_INDEX_PATH")
    seed, stories = release_files.curated_files("ontario-reports", _registry())
    assert str(seed).endswith("seed_questions.ontario.jsonl") and str(stories).endswith("stories.ontario.json")


def test_the_boot_plans_a_new_scope_with_no_code_naming_it(tmp_path, monkeypatch):
    registry = _registry()

    class Resolved:
        db_path = tmp_path / "ontario-reports" / "ontario.db"
        index_path = tmp_path / "ontario-reports" / "index" / "vectors_ontario.db"

    monkeypatch.setattr(provision.scopes, "resolve_scope", lambda name: Resolved)
    plan = provision.plan_scope("ontario-reports", registry, numpy_backend=True)
    kinds = sorted(j.kind for j in plan.jobs)
    assert kinds == ["db", "dense_ids", "dense_manifest", "dense_matrix", "facts"]
    assert plan.stubs == [(Resolved.index_path, registry["scopes"]["ontario-reports"]["r2"]["index_sha256"])]
    facts_job = next(j for j in plan.jobs if j.kind == "facts")
    assert facts_job.dest == tmp_path / "ontario-reports" / "ontario.facts.json"
    sqlite_plan = provision.plan_scope("ontario-reports", registry, numpy_backend=False)
    assert sorted(j.kind for j in sqlite_plan.jobs) == ["db", "facts", "index"]


def test_the_published_registry_describes_both_collections_completely():
    files = release_files.all_files()
    for scope in release_files.scope_names():
        kinds = {f.kind for f in files if f.scope == scope}
        assert {"db", "index", "dense_matrix", "dense_ids", "dense_manifest", "facts"} <= kinds
        assert all(len(f.sha256) == 64 for f in files if f.scope == scope)
        seed, stories = release_files.curated_files(scope)
        assert seed is not None and seed.exists() and stories is not None and stories.exists()


def test_precomputed_facts_are_used_only_for_the_published_database_and_current_code(tmp_path):
    import json
    import sqlite3
    from archive_debugger.api import app as app_mod
    from archive_debugger.api.cache import canonical_data_sha256
    from archive_debugger.ingest import db
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    conn.execute("INSERT INTO items (item_id, title, dated, year) VALUES ('a', 'a', 1, 1980)")
    conn.commit()
    window = {"min_year": 1960, "max_year": 2009}
    computed = app_mod.compute_data_facts(conn, window)
    doc = app_mod.facts_document("pilot", conn, canonical_data_sha256("pilot")["db"], window)
    doc["corpus"]["items"] = 999_999                                       # a marker: proves the file was read
    path = release_files.facts_path(civ)
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert app_mod.load_or_compute_data_facts("pilot", conn, civ, window)["corpus"]["items"] == 999_999
    for change in ({"facts_version": "older"}, {"db_sha256": "0" * 64}, {"pilot_window": {"min_year": 1900}}):
        path.write_text(json.dumps({**doc, **change}), encoding="utf-8")
        assert app_mod.load_or_compute_data_facts("pilot", conn, civ, window) == computed
    conn.close()
