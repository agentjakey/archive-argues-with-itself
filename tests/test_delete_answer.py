"""The deletion helper finds the same key the engine Worker and the engine store an answer under."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from archive_debugger.api import cache as answer_cache

REPO = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("delete_answer", REPO / "scripts" / "v2" / "delete_answer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_keys_match_the_published_worker_context():
    mod = _module()
    config = json.loads((REPO / "worker" / "engine" / "src" / "generated" / "engine_config.json").read_text(encoding="utf-8"))
    question = "  How did   tobacco policy change? "
    keys = mod.keys_for(question, None, sorted(config["scopes"]))
    for name, key in keys.items():
        assert key == answer_cache.content_key(config["scopes"][name]["context"], question, None)


def test_the_command_deletes_only_visitor_rows():
    mod = _module()
    command = mod.delete_command(["a" * 64], "production")
    assert "curated = 0" in command and "--remote --env production" in command and "DELETE FROM answers_v2" in command
