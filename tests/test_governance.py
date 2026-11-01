"""The governance register and its enforcement (docs/formats/governance.md): empty by default,
fixtures refused in production, and nothing from a restricted record leaks into an answer, the
evidence, the stored cache row or the model's input."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archive_debugger import governance
from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM

from tests.test_api import _app, _retriever

REPO = Path(__file__).resolve().parent.parent
SECRET = "sacred ceremony location"


def policy(pid="fixture-1", items=("b",), collections=(), restrict=("retrieve", "generate", "export"), fixture=True, lc=None):
    return {"format": 1, "policy_id": pid, "targets": {"items": list(items), "collections": list(collections)},
            "restrict": list(restrict), "authority": governance.FIXTURE_AUTHORITY,
            "basis": "test", "contact": "", "display": {"label": "Restricted (test)", "local_contexts": lc},
            "entered_by": "test", "entered_at": "2026-11-01T00:00:00Z", "fixture": fixture}


def write(path: Path, rows: list) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_the_committed_register_is_empty():
    assert governance.load(governance.DEFAULT_REGISTER).empty
    assert governance.load(REPO / "config" / "governance" / "policies.jsonl").digest == ""


def test_production_refuses_fixtures_and_the_fixture_loader_refuses_real_records(tmp_path):
    with pytest.raises(governance.RegisterError, match="fixture"):
        governance.load(write(tmp_path / "p.jsonl", [policy()]))
    real = policy(fixture=False)
    with pytest.raises(governance.RegisterError, match="not a fixture"):
        governance.load(write(tmp_path / "f.jsonl", [real]), fixtures=True)
    assert not governance.load(write(tmp_path / "r.jsonl", [real])).empty


def test_bad_records_are_refused(tmp_path):
    for bad in (dict(policy(fixture=False), restrict=["read"]), dict(policy(fixture=False), targets={"items": []}),
                policy(fixture=False, lc={"label_ids": ["x"]})):
        with pytest.raises(governance.RegisterError):
            governance.load(write(tmp_path / "bad.jsonl", [bad]))
    with pytest.raises(governance.RegisterError, match="duplicate"):
        governance.load(write(tmp_path / "dup.jsonl", [policy(fixture=False), policy(fixture=False)]))


def test_local_contexts_labels_come_only_from_the_record():
    reg = governance.from_records([policy()], fixtures=True)
    assert reg.policies[0].notice()["local_contexts"] is None
    lc = {"project_id": "p1", "label_ids": ["l1"], "label_names": ["Attribution"]}
    reg = governance.from_records([policy(lc=lc)], fixtures=True)
    assert reg.policies[0].notice()["local_contexts"] == lc


class Recording(StubLLM):
    """Records every prompt the model is given; cites the public document's first passage."""

    def __init__(self):
        super().__init__(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=["a#0:0"])]))
        self.seen: list = []

    def draft(self, system, user):
        self.seen.append(user)
        return super().draft(system, user)


def _restricted_app(tmp_path, reg, llm=None):
    r, _ = _retriever(tmp_path, [("a", 1990, "ontario"), ("b", 1991, "ontario"), ("c", 1992, "ontario"), ("d", 1993, "ontario")])
    # the restricted document holds words the public one does not
    conn = sqlite3.connect(r.cfg.db_path)
    conn.execute("UPDATE passages SET text = ? WHERE item_id = 'b'", (f"vaccination hospital programme {SECRET}",))
    conn.execute("INSERT INTO passages_fts(passages_fts) VALUES ('rebuild')")
    conn.commit()
    conn.close()
    kw = {"governance_register": reg}
    if llm is not None:
        kw["llm"] = llm
    return _app(tmp_path, r, **kw)


def test_restricted_documents_never_reach_retrieval_the_model_the_reader_or_the_cache(tmp_path):
    reg = governance.from_records([policy()], fixtures=True)
    llm = Recording()
    app = _restricted_app(tmp_path, reg, llm)
    with TestClient(app) as c:
        body = c.post("/ask", json={"question": "vaccination hospital programme"}).json()
        raw = json.dumps(body)
        assert SECRET not in raw and '"b#' not in raw
        assert llm.seen and all("b#" not in p and SECRET not in p for p in llm.seen)
        assert body["governance"]["restricted"][0]["policy_id"] == "fixture-1"
        assert body["governance"]["restricted"][0]["authority"].startswith("Synthetic test authority")
    rows = sqlite3.connect(tmp_path / "cache" / "answers.db").execute("SELECT response_json FROM answers_v2").fetchall() \
        if (tmp_path / "cache" / "answers.db").exists() else []
    assert all(SECRET not in r[0] and '"b#' not in r[0] for r in rows)


def test_a_question_only_the_restricted_document_answers_is_restricted_with_no_model_call(tmp_path):
    reg = governance.from_records([policy(items=("a", "b", "c", "d"))], fixtures=True)
    llm = Recording()
    with TestClient(_restricted_app(tmp_path, reg, llm)) as c:
        body = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert body["answer"]["abstained"] and "restricted" in body["answer"]["text"]
    assert body["governance"]["restricted"] and body["evidence"] == [] and llm.seen == []


def test_a_collection_wide_retrieval_restriction_searches_nothing(tmp_path):
    reg = governance.from_records([policy(items=(), collections=("pilot",), restrict=("retrieve",))], fixtures=True)
    with TestClient(_restricted_app(tmp_path, reg)) as c:
        body = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert body["governance"]["restricted"][0]["policy_id"] == "fixture-1" and body["evidence"] == []


def test_the_register_digest_joins_the_cache_context(tmp_path):
    from archive_debugger.api.app import cache_context
    gcfg = {"provider": "stub", "model": "m", "temperature": 0.0, "max_tokens": 10, "top_k": 5}
    data = {"db": "a" * 64, "index": "b" * 64}
    base = cache_context("pilot", data, {}, gcfg, "stub", "m")
    assert cache_context("pilot", data, {}, gcfg, "stub", "m", "") == base
    digest = governance.from_records([policy()], fixtures=True).digest
    assert digest and cache_context("pilot", data, {}, gcfg, "stub", "m", digest) != base
