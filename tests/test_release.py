"""The static release gates (scripts/v2/build_release.py): the committed data shards pass, and a
release that was tampered with, lost a dated note, recorded a limited-mode answer, carries a secret
or exceeds the asset limits is refused."""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("build_release", REPO / "scripts" / "v2" / "build_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def release(tmp_path):
    mod = _module()
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Archive Argues With Itself</title>", encoding="utf-8")
    (web / "assets" / "index.js").write_text("console.log('reading room');", encoding="utf-8")
    out = tmp_path / "release"
    mod.assemble("test-release", web, REPO / "site" / "data", REPO / "site" / "static", out, "https://api.archiveargues.org")
    return mod, out


def _remanifest(mod, out: Path) -> None:
    """Rewrite the manifest after a deliberate change, so the test reaches the content gates."""
    manifest = json.loads((out / mod.MANIFEST).read_text(encoding="utf-8"))
    manifest["files"] = mod.file_table(out)
    (out / mod.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def test_committed_shards_pass(release):
    mod, out = release
    assert mod.gate(out, REPO / "config" / "release_allow_missing.json") == []
    assert "connect-src 'self' https://api.archiveargues.org" in (out / "_headers").read_text(encoding="utf-8")


def test_a_changed_file_is_refused(release):
    mod, out = release
    (out / "assets" / "index.js").write_text("console.log('changed after the build');", encoding="utf-8")
    assert any("sha256 differs" in p for p in mod.gate(out, REPO / "config" / "release_allow_missing.json"))


def test_a_lost_note_and_a_recorded_limited_mode_are_refused(release):
    mod, out = release
    notes = json.loads((out / "data" / "editorial_notes.json").read_text(encoding="utf-8"))
    answer_note = next(n for n in notes["notes"] if n["target"]["kind"] == "answer")
    index = json.loads((out / "data" / "pilot" / "answers" / "index.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["answers"] if e["question"] == answer_note["target"]["question"])
    path = out / "data" / "pilot" / entry["file"]
    body = json.loads(path.read_text(encoding="utf-8"))
    body["editorial_notes"] = []
    body["degraded"] = {"reason": "model_unreachable", "live_url": "https://archiveargues.org"}
    path.write_text(json.dumps(body), encoding="utf-8")
    _remanifest(mod, out)
    problems = mod.gate(out, REPO / "config" / "release_allow_missing.json")
    assert any(f"dated note {answer_note['id']} is not attached" in p for p in problems)
    assert any("limited-mode response was recorded" in p for p in problems)


def test_a_citation_without_its_page_is_refused(release):
    mod, out = release
    index = json.loads((out / "data" / "pilot" / "answers" / "index.json").read_text(encoding="utf-8"))
    for entry in index["answers"]:
        path = out / "data" / "pilot" / entry["file"]
        body = json.loads(path.read_text(encoding="utf-8"))
        if body["answer"]["verified_citations"]:
            body["evidence"] = [r for r in body["evidence"]
                                if r["passage_id"] != body["answer"]["verified_citations"][0]["passage_id"]]
            path.write_text(json.dumps(body), encoding="utf-8")
            break
    _remanifest(mod, out)
    assert any("is not in its evidence" in p for p in mod.gate(out, REPO / "config" / "release_allow_missing.json"))


def test_secrets_size_and_unlisted_missing_answers_are_refused(release, tmp_path):
    mod, out = release
    (out / "assets" / "leak.js").write_text("const key = 'sk-ant-api03-" + "x" * 40 + "';", encoding="utf-8")
    (out / "assets" / "huge.bin").write_bytes(b"\0" * (mod.MAX_FILE_BYTES + 1))
    _remanifest(mod, out)
    strict = tmp_path / "allow_none.json"
    strict.write_text("{}", encoding="utf-8")
    problems = mod.gate(out, strict)
    assert any("looks like a secret" in p for p in problems)
    assert any("25 MiB" in p for p in problems)
    assert any("microlog: curated questions without a recorded answer" in p for p in problems)


def test_publish_refuses_a_failing_release_before_any_upload(release, monkeypatch):
    mod, out = release
    (out / "index.html").write_text("tampered", encoding="utf-8")
    calls = []
    monkeypatch.setattr(mod, "wrangler", lambda args: calls.append(args))
    assert mod.publish(out, "staging", REPO / "config" / "release_allow_missing.json") == 1
    assert calls == []
