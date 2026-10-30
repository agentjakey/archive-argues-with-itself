"""Content-addressed answer cache (format v2): the key, the shared vectors, privacy and retention,
and a stored answer surviving a cold start on a fresh copy of the data."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from archive_debugger.api import cache as answer_cache
from archive_debugger.retrieve import search
from archive_debugger.retrieve.embed import StubEmbedder

from test_api import _app, _retriever

VECTORS = Path("config/cache_key_vectors.json")


def _load_vector_module():
    spec = importlib.util.spec_from_file_location("make_cache_vectors", Path("scripts/v2/make_cache_vectors.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shared_vectors_match_the_python_key():
    """The committed vectors are what the Python key produces today; the Worker tests read the same
    file, so the two implementations cannot drift apart silently."""
    committed = json.loads(VECTORS.read_text(encoding="ascii"))
    assert committed == _load_vector_module().build()
    for v in committed["vectors"]:
        assert answer_cache.content_key(committed["context"], v["question"], v["filters"]) == v["key"]
        assert answer_cache.normalize_question(v["question"]) == v["normalized_question"]


def test_normalization_rules():
    n = answer_cache.normalize_question
    assert n("  vaccination \t hospital\n") == "vaccination hospital"
    assert n("Que\u0301bec") == n("Qu\u00e9bec")                       # NFC
    assert n("Vaccination") != n("vaccination")                             # case is kept
    assert n("public\u00a0health") != n("public health")                    # only control characters become spaces
    assert n("a\ud800b") == "a\ufffdb"
    f = answer_cache.canonical_filters
    assert f({"jurisdiction": " alberta ", "doc_type": "", "colour": "x"}) == {"jurisdiction": "alberta"}
    assert f({"min_ocr": 0}) == {} and f({"min_ocr": 1}) == f({"min_ocr": "1.0"}) == {"min_ocr": "1.0000"}
    assert f(None) == {}


def test_key_depends_on_context_question_and_filters():
    k = answer_cache.content_key
    assert k("c1", "q", {}) != k("c2", "q", {})
    assert k("c1", "q", {}) != k("c1", "q", {"jurisdiction": "alberta"})
    assert k("c1", " q ", None) == k("c1", "q", {})


def test_context_requires_published_hashes():
    import pytest
    with pytest.raises(ValueError):
        answer_cache.context_hash(scope="pilot", data_sha256={"db": "a" * 64}, retrieve={}, provider="stub",
                                  model="m", prompt_sha256="p", top_k=12, temperature=None)
    hashes = answer_cache.canonical_data_sha256("pilot")
    assert len(hashes["db"]) == len(hashes["index"]) == 64


def test_visitor_rows_keep_no_question_and_expire(tmp_path):
    store = answer_cache.LocalCache(tmp_path / "answers.db")
    old = datetime.now(timezone.utc) - timedelta(days=answer_cache.RETENTION_DAYS + 1)
    visitor = answer_cache.make_record(key="v", scope="pilot", context="c", response={"answer": {}, "evidence": []},
                                       extras_version="e", curated_question=None)
    stale = answer_cache.make_record(key="s", scope="pilot", context="c", response={"answer": {}, "evidence": []},
                                     extras_version="e", curated_question=None, now=old)
    curated = answer_cache.make_record(key="k", scope="pilot", context="c", response={"answer": {}, "evidence": []},
                                       extras_version="e", curated_question="a seed question", now=old)
    for record in (visitor, stale, curated):
        store.put(record)
    assert visitor["question"] is None and visitor["expires_at"] is not None
    assert curated["question"] == "a seed question" and curated["expires_at"] is None
    assert store.get("v") is not None and store.get("k") is not None
    assert store.get("s") is None                                            # expired: never served
    assert store.purge_expired() == 1
    assert store.count() == {"rows": 2, "curated": 1, "response_bytes": store.count()["response_bytes"]}
    store.close()


def test_answer_survives_a_cold_start_on_a_fresh_copy(tmp_path):
    """Ask once, then copy the data files to an empty directory (new paths, new mtimes, an extra byte
    on the index) and start a new app on the copy with the same cache: the stored answer is served."""
    from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM
    r, _ = _retriever(tmp_path, [("a", 1974, "alberta"), ("b", 1999, "alberta")])
    hits = r.search("vaccination hospital", top_k=12)
    llm = StubLLM(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=[hits[0]["passage_id"]])]))
    cache_db = tmp_path / "cache" / "answers.db"
    with TestClient(_app(tmp_path, r, llm=llm)) as c:
        first = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert first["answer"]["cached"] is None

    fresh = tmp_path / "fresh-disk"
    fresh.mkdir()
    shutil.copyfile(r.cfg.db_path, fresh / "civic.db")
    shutil.copyfile(r.cfg.index_path, fresh / "vectors.db")
    cfg = replace(r.cfg, db_path=fresh / "civic.db", index_path=fresh / "vectors.db")
    r2 = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    with TestClient(_app(tmp_path, r2, llm=llm)) as c:
        again = c.post("/ask", json={"question": "  vaccination   hospital "}).json()
    assert again["answer"]["cached"] is not None
    assert again["answer"]["text"] == first["answer"]["text"]


def test_only_curated_questions_are_stored_with_text(tmp_path):
    r, seed = _retriever(tmp_path, [("a", 1990, "alberta")], seed_questions=[("q1", None)])
    cache_db = tmp_path / "cache" / "answers.db"
    with TestClient(_app(tmp_path, r, seed_path=seed)) as c:
        c.post("/ask", json={"question": "vaccination hospital", "filters": {"jurisdiction": "alberta"}})   # the seed
        c.post("/ask", json={"question": "a visitor asks about vaccination hospital"})
    rows = sqlite3.connect(cache_db).execute("SELECT curated, question, expires_at FROM answers_v2 ORDER BY curated").fetchall()
    assert rows[0][0] == 0 and rows[0][1] is None and rows[0][2] is not None
    assert rows[1] == (1, "vaccination hospital", None)
    stored = sqlite3.connect(cache_db).execute("SELECT response_json FROM answers_v2").fetchall()
    assert all("a visitor asks" not in body for (body,) in stored)


def test_environment_wins_over_dotenv_and_values_are_never_logged(tmp_path, monkeypatch):
    from archive_debugger.local_env import load_local_env
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-file-secret\nCIVIC_CACHE_TOKEN=file-token-secret\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell-secret")
    monkeypatch.delenv("CIVIC_CACHE_TOKEN", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    lines = []
    sources = load_local_env(env_file, log=lines.append)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell-secret"
    assert os.environ["CIVIC_CACHE_TOKEN"] == "file-token-secret"
    assert sources["ANTHROPIC_API_KEY"] == "environment" and sources["CIVIC_CACHE_TOKEN"] == ".env"
    assert sources["R2_ACCESS_KEY_ID"] == "unset"
    assert len(lines) == 1 and "secret" not in lines[0].replace("secrets present", "")
    os.environ.pop("CIVIC_CACHE_TOKEN", None)          # set by the .env load above, not by monkeypatch
