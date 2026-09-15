"""Scope registry, scope-by-name resolution, the fence, and the one-command builder.

These prove the deliverable acceptance without touching the real pilot databases:
  - no scope active resolves byte-identically to the legacy behavior;
  - the pilot is the inherit (default) scope and resolves via config + env;
  - a non-inherit scope pins its own paths, IGNORES the CIVIC_* env, and is fenced so it
    cannot open another scope's databases;
  - the builder chains loader -> build -> normalize -> sections -> embed for a scope,
    resumably, writing only under that scope's paths.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from archive_debugger import build_scope, scopes
from archive_debugger.ingest import build as build_mod
from archive_debugger.ingest import db
from archive_debugger.retrieve.config import load_retrieve_config

REPO = Path(__file__).resolve().parents[1]
FX = Path(__file__).parent / "fixtures" / "ocr"
CONFIG_CSVS = ("jurisdiction_rules.csv", "issuer_aliases.csv", "doctype_rules.csv")


# --------------------------------------------------------------------------- #
# Registry + resolution
# --------------------------------------------------------------------------- #


def test_pilot_is_the_inherit_default():
    scope = scopes.resolve_scope("pilot", registry_path=REPO / "config/scopes.toml")
    assert scope.inherit is True
    assert scope.config_path == Path("config/pilot.toml")
    # inherit resolves via config + env; conftest unsets CIVIC_*, so it is the config value.
    assert scope.db_path == Path("civic.db")
    assert scope.index_path == Path("index/vectors.db")


def test_microlog_registry_paths_and_drift_guard():
    scope = scopes.resolve_scope("microlog", registry_path=REPO / "config/scopes.toml")
    assert scope.inherit is False
    assert scope.db_path == Path("data/exploration/microlog/civic_microlog.db")
    assert scope.index_path == Path("data/exploration/microlog/index/vectors_microlog.db")
    assert scope.cache_dir == Path("data/exploration/microlog/raw")
    # derived working dirs live under one isolated root
    assert scope.harvest_dir == Path("data/exploration/microlog/harvest")
    assert scope.items_path == Path("data/exploration/microlog/harvest/items.jsonl")


def test_unknown_scope_raises():
    with pytest.raises(scopes.ScopeError):
        scopes.resolve_scope("nope", registry_path=REPO / "config/scopes.toml")


def test_no_scope_is_byte_identical():
    # No scope active: resolution is exactly the legacy config-value behavior.
    assert scopes.active_scope() is None
    assert db.resolve_db_path("config/pilot.toml") == Path("civic.db")
    cfg = load_retrieve_config(Path("config/pilot.toml"))
    assert cfg.db_path == Path("civic.db") and cfg.index_path == Path("index/vectors.db")


# --------------------------------------------------------------------------- #
# Fence: env ignored, pilot databases unreachable
# --------------------------------------------------------------------------- #


def test_active_scope_ignores_civic_env(monkeypatch):
    # The .env footgun: CIVIC_DB_PATH set to the pilot's store. A fenced scope must ignore it.
    monkeypatch.setenv("CIVIC_DB_PATH", r"C:\civic-data\civic.db")
    monkeypatch.setenv("CIVIC_INDEX_PATH", r"C:\civic-data\index\vectors.db")
    scope = scopes.resolve_scope("microlog", registry_path=REPO / "config/scopes.toml")
    with scopes.activate(scope):
        assert db.resolve_db_path(scope.config_path) == scope.db_path
        cfg = load_retrieve_config(scope.config_path)
        assert cfg.db_path == scope.db_path
        assert cfg.index_path == scope.index_path


def test_fence_blocks_foreign_db(tmp_path):
    # A temp registry whose scope's db lives under tmp; connecting anywhere else raises.
    reg = _write_registry(tmp_path)
    scope = scopes.resolve_scope("fixture", registry_path=reg)
    pilot_like = tmp_path / "civic.db"           # stand-in for the pilot store
    scope.db_path.parent.mkdir(parents=True, exist_ok=True)
    with scopes.activate(scope):
        # its own database opens fine
        conn = db.connect(scope.db_path)
        conn.close()
        # any other database is refused, even one that exists on disk
        pilot_like.write_bytes(b"")
        with pytest.raises(scopes.ScopeViolation):
            db.connect(pilot_like)


def test_no_fence_without_active_scope(tmp_path):
    # Guard is a strict no-op with no scope active (byte-identical connect).
    assert scopes.active_scope() is None
    conn = db.connect(tmp_path / "any.db")
    conn.close()


# --------------------------------------------------------------------------- #
# One-command builder
# --------------------------------------------------------------------------- #


def test_builder_refuses_the_frozen_default():
    # The pilot is never rebuilt through the builder.
    rc = build_scope.build("pilot")
    assert rc == 2


def test_builder_chains_and_resumes(tmp_path, monkeypatch, capsys):
    reg = _write_registry(tmp_path)
    monkeypatch.setattr(scopes, "REGISTRY_PATH", reg)
    # env set to the pilot store: the fenced build must still land only under tmp.
    monkeypatch.setenv("CIVIC_DB_PATH", r"C:\civic-data\civic.db")
    monkeypatch.setenv("CIVIC_INDEX_PATH", r"C:\civic-data\index\vectors.db")

    scope = scopes.resolve_scope("fixture", registry_path=reg)
    _seed_harvest_output(scope)

    rc = build_scope.build("fixture", from_stage="loader", embedder_override="stub")
    assert rc == 0
    out = capsys.readouterr().out
    assert "[build_scope] DONE" in out
    for stage in ("loader", "build", "normalize", "sections", "embed"):
        assert f"[{stage}] OK" in out
    # structured status only: no fixture passage text leaked to stdout
    assert "Ontario hospital funding" not in out

    civ = scope.db_path
    vec = scope.index_path
    assert civ.exists() and vec.exists()
    c = sqlite3.connect(civ)
    items = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    passages = c.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    c.close()
    assert items == 2 and passages >= 2
    v = sqlite3.connect(vec)
    vectors = v.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0]
    v.close()
    assert vectors == passages

    # the fenced build wrote ONLY under the scope root, never the pilot store
    assert not (tmp_path / "civic.db").exists()

    # resume: rerun is safe and adds no new vectors
    rc2 = build_scope.build("fixture", from_stage="loader", embedder_override="stub")
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "embed] OK  new_vectors=0" in out2
    v = sqlite3.connect(vec)
    assert v.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0] == vectors
    v.close()


# --------------------------------------------------------------------------- #
# Fixture helpers
# --------------------------------------------------------------------------- #


def _write_registry(tmp_path: Path) -> Path:
    """A temp registry + config for a fully isolated 'fixture' scope under tmp_path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_CSVS:
        shutil.copyfile(REPO / "config" / name, config_dir / name)

    scope_root = tmp_path / "scope"
    db_path = scope_root / "civic_fixture.db"
    index_path = scope_root / "index" / "vectors_fixture.db"
    cache_dir = scope_root / "raw"

    config_path = config_dir / "fixture.toml"
    config_path.write_text(
        "[corpus]\n"
        'topic = "fixture"\n'
        'query = "health"\n'
        'mediatype = "texts"\n'
        "[corpus.window]\n"
        "start_year = 1960\n"
        "end_year = 2009\n"
        "[corpus.collections]\n"
        'clean = ["fixturecollection"]\n'
        "reserve = []\n"
        "[corpus.limits]\n"
        "usable_floor = 1\n"
        "[harvest]\n"
        'user_agent_contact = ""\n'
        'fields = "identifier"\n'
        f'cache_dir = "{cache_dir.as_posix()}"\n'
        "[index]\n"
        f'db_path = "{db_path.as_posix()}"\n'
        'embedding_model = "stub-model"\n'
        "embedding_dim = 8\n"
        "[retrieve]\n"
        f'index_path = "{index_path.as_posix()}"\n'
        'embedder = "stub"\n'
        "batch_size = 16\n",
        encoding="utf-8",
    )

    registry = tmp_path / "scopes.toml"
    registry.write_text(
        'default = "pilot"\n'
        "[scopes.pilot]\n"
        'config = "config/pilot.toml"\n'
        "inherit = true\n"
        "[scopes.fixture]\n"
        f'config = "{config_path.as_posix()}"\n'
        f'db_path = "{db_path.as_posix()}"\n'
        f'index_path = "{index_path.as_posix()}"\n',
        encoding="utf-8",
    )
    return registry


def _seed_harvest_output(scope: scopes.Scope) -> None:
    """Stand in for the harvest stage: two items with cached DjVuXML OCR."""
    scope.harvest_dir.mkdir(parents=True, exist_ok=True)
    for item_id in ("itemA", "itemB"):
        dest = build_mod.content_path(scope.cache_dir, f"md5_{item_id}", f"{item_id}_djvu.xml")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FX / "sample_djvu.xml", dest)
    records = [
        {
            "identifier": item_id,
            "title": f"Report {item_id}",
            "creator_raw": "Ministry of Health",
            "publisher_raw": "Government of Ontario",
            "date_raw": "1985",
            "collection_raw": ["fixturecollection"],
            "language": "eng",
            "mediatype": "texts",
            "ocr_format": "DjVuXML",
            "segmentation_source": "djvuxml",
            "ocr_file": {"md5": f"md5_{item_id}", "name": f"{item_id}_djvu.xml"},
            "ocr_file_ref": f"{item_id}_djvu.xml",
            "has_printed_page_map": False,
            "page_count": 2,
            "details_url": f"https://archive.org/details/{item_id}",
        }
        for item_id in ("itemA", "itemB")
    ]
    with scope.items_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
