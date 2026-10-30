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
    (web / "index.html").write_text("<!doctype html><html><head><title>Archive Argues With Itself</title></head>"
                                    "<body></body></html>", encoding="utf-8")
    (web / "assets" / "index.js").write_text("console.log('reading room');", encoding="utf-8")
    out = tmp_path / "release"
    mod.assemble("test-release", web, REPO / "site" / "data", REPO / "site" / "static", out, "https://api.archiveargues.org")
    return mod, out


def _data(mod, out: Path) -> Path:
    """The release's data folder, named by the hash of its content (from the manifest)."""
    return out / "data" / json.loads((out / mod.MANIFEST).read_text(encoding="utf-8"))["data_version"]


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
    notes = json.loads((_data(mod, out) / "editorial_notes.json").read_text(encoding="utf-8"))
    answer_note = next(n for n in notes["notes"] if n["target"]["kind"] == "answer")
    index = json.loads((_data(mod, out) / "pilot" / "answers" / "index.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["answers"] if e["question"] == answer_note["target"]["question"])
    path = _data(mod, out) / "pilot" / entry["file"]
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
    index = json.loads((_data(mod, out) / "pilot" / "answers" / "index.json").read_text(encoding="utf-8"))
    for entry in index["answers"]:
        path = _data(mod, out) / "pilot" / entry["file"]
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
    index_path = _data(mod, out) / "microlog" / "answers" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["answers"][0]["file"] = None                                     # a curated question with no answer
    index_path.write_text(json.dumps(index), encoding="utf-8")
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


def test_caching_headers_and_the_versioned_data_folder(release):
    mod, out = release
    version = json.loads((out / mod.MANIFEST).read_text(encoding="utf-8"))["data_version"]
    assert len(version) == 16 and (out / "data" / version / "scopes.json").exists()
    assert f'<meta name="archive-data" content="/data/{version}" />' in (out / "index.html").read_text(encoding="utf-8")
    assert version == mod.data_version(REPO / "site" / "data")                  # the same data, the same folder
    rules = {}
    current = None
    for line in (out / "_headers").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith((" ", "#")):
            current = line.strip()
            rules[current] = []
        elif line.startswith("  ") and current:
            rules[current].append(line.strip())
    assert "Cache-Control: public, max-age=31536000, immutable" in rules["/assets/*"]
    assert "Cache-Control: public, max-age=31536000, immutable" in rules["/data/*"]
    for path in ("/", "/index.html", "/release-manifest.json"):
        assert "Cache-Control: no-cache" in rules[path]
    assert not any(r.startswith("Cache-Control") for r in rules["/*"])        # no rule that would merge into others
