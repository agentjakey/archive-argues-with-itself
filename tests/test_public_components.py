"""scripts/v2/public_components.py: licence policy, the retry rule, and a subset built from canned
replies. No test reaches a real host."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test tried to reach the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _module():
    spec = importlib.util.spec_from_file_location("public_components",
                                                  REPO / "scripts" / "v2" / "public_components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fetcher(mod, replies, cache_dir=None):
    calls = []

    def transport(url):
        calls.append(url)
        for prefix, queue in replies.items():
            if url.startswith(prefix):
                reply = queue.pop(0) if len(queue) > 1 else queue[0]
                return reply
        raise AssertionError(f"unexpected url {url}")

    fetcher = mod.Fetcher(transport=transport, sleeper=lambda seconds: None, cache_dir=cache_dir, retries=3)
    return fetcher, calls


def test_licence_policy_refuses_noncommercial_missing_and_changed():
    mod = _module()
    assert mod.licence_decision(["mit"], ["mit"])[0] == "permitted"
    assert mod.licence_decision(["cc-by-sa-4.0"], ["cc-by-sa-4.0"])[0] == "permitted"
    decision, reason = mod.licence_decision(["cc-by-nc-4.0"], None)
    assert decision == "refused" and "non-commercial" in reason
    assert mod.licence_decision(["cc-by-nd-4.0"], None)[0] == "refused"
    assert mod.licence_decision([], None) == ("refused", "no licence grant found at the source")
    assert mod.licence_decision(["other"], None)[0] == "refused"
    assert mod.licence_decision(["gpl-3.0"], None)[0] == "refused"
    decision, reason = mod.licence_decision(["apache-2.0"], ["mit"])
    assert decision == "refused" and "review it again" in reason


def test_retry_rule_retries_5xx_and_transient_server_text_but_raises_other_4xx():
    mod = _module()
    server = mod.DS_SERVER + "rows?x=1"
    fetcher, calls = _fetcher(mod, {server: [(503, b""), (200, b'{"error":"the dataset index is loading"}'),
                                             (200, b'{"rows": []}')]})
    assert fetcher.get_json(server) == {"rows": []}
    assert len(calls) == 3

    fetcher, calls = _fetcher(mod, {"https://huggingface.co/api/": [(404, b"not found")]})
    with pytest.raises(mod.FetchError):
        fetcher.get("https://huggingface.co/api/datasets/nope")
    assert len(calls) == 1

    fetcher, calls = _fetcher(mod, {server: [(502, b"")]})
    with pytest.raises(mod.FetchError, match="gave up"):
        fetcher.get(server)
    assert len(calls) == 4


def test_cached_reply_is_not_fetched_again(tmp_path):
    mod = _module()
    url = "https://huggingface.co/api/datasets/x"
    fetcher, calls = _fetcher(mod, {url: [(200, b"{}")]}, cache_dir=tmp_path)
    fetcher.get(url)
    fetcher.get(url)
    assert len(calls) == 1


def _hf_info(sha, licence):
    return (200, json.dumps({"sha": sha, "cardData": {"license": licence}, "siblings": []}).encode())


def _gh_replies(licence):
    return {"https://api.github.com/repos/DataScienceUIBK/ChroniclingAmericaQA/commits/":
            [(200, json.dumps({"sha": "c0ffee"}).encode())],
            "https://api.github.com/repos/DataScienceUIBK/ChroniclingAmericaQA":
            [(200, json.dumps({"default_branch": "main",
                               "license": {"spdx_id": licence} if licence else None}).encode())]}


def test_chroniclingamericaqa_subset_and_manifest(tmp_path):
    mod = _module()
    rows = [{"row_idx": index, "truncated_cells": [],
             "row": {field: f"{field}-{index}" for field in mod.CAQA_FIELDS}} for index in range(10)]
    replies = {mod.HF_API: [_hf_info("abc123", "mit")],
               mod.DS_SERVER + "size": [(200, json.dumps({"size": {"splits": [
                   {"split": "test", "num_rows": 40}]}}).encode())],
               mod.DS_SERVER + "rows": [(200, json.dumps({"rows": rows}).encode())]}
    replies.update(_gh_replies("MIT"))
    fetcher, calls = _fetcher(mod, replies)
    manifest = mod.build_chroniclingamericaqa(fetcher, tmp_path, seed=7, items=20, block=10)

    assert manifest["status"] == "complete"
    assert manifest["counts"]["items"] == 20
    assert [s["decision"] for s in manifest["sources"]] == ["permitted", "permitted"]
    assert manifest["sources"][0]["revision"] == "abc123"
    written = (tmp_path / "items.jsonl").read_bytes()
    assert manifest["files"][0]["sha256"] == hashlib.sha256(written).hexdigest()
    assert b"\r\n" not in written
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["seed"] == 7 and on_disk["purpose"].startswith("Component check")


def test_miracl_subset_keeps_going_when_a_filter_batch_fails(tmp_path):
    mod = _module()
    info = {"sha": "rev1", "cardData": {"license": ["apache-2.0"]},
            "siblings": [{"rfilename": mod.MIRACL_TOPICS_FILE, "size": 100},
                         {"rfilename": mod.MIRACL_QRELS_FILE, "size": 100}]}
    topics = "q1\tpremiere question\nq2\tdeuxieme question\nq3\tsans jugement\n"
    qrels = "q1 Q0 10#0 1\nq1 Q0 10#1 0\nq2 Q0 20#0 1\n"
    found = {"rows": [{"row_idx": 5, "truncated_cells": [],
                       "row": {"docid": "10#0", "title": "T", "text": "texte"}},
                      {"row_idx": 6, "truncated_cells": [],
                       "row": {"docid": "10#1", "title": "T", "text": "autre"}}],
             "num_rows_total": 2, "partial": True}
    calls = []

    def transport(url):
        calls.append(url)
        if url.startswith(mod.HF_API):
            return 200, json.dumps(info).encode()
        if url.endswith(mod.MIRACL_TOPICS_FILE):
            return 200, topics.encode()
        if url.endswith(mod.MIRACL_QRELS_FILE):
            return 200, qrels.encode()
        if "20%230" in url:
            return 500, b'{"error":"temporary internal issue"}'
        return 200, json.dumps(found).encode()

    fetcher = mod.Fetcher(transport=transport, sleeper=lambda seconds: None, cache_dir=None, retries=1)
    manifest = mod.build_miracl_fr(fetcher, tmp_path, seed=3, queries=2, batch=2)

    assert manifest["counts"]["queries"] == 2
    assert manifest["counts"]["judgments"] == 3
    assert manifest["counts"]["passages_written"] == 2
    assert manifest["missing_docids"] == ["20#0"]
    assert manifest["counts"]["filter_batches_failed"] == 1
    assert manifest["filter_index_partial"] is True
    assert manifest["status"] == "partial"
    assert any("rev1" in url for url in calls if url.endswith(".tsv"))


def test_refused_licence_downloads_no_data(tmp_path):
    mod = _module()
    replies = {mod.HF_API: [_hf_info("abc123", "cc-by-nc-4.0")]}
    replies.update(_gh_replies("MIT"))
    fetcher, calls = _fetcher(mod, replies)
    manifest = mod.build_chroniclingamericaqa(fetcher, tmp_path, seed=7)

    assert manifest["status"] == "refused"
    assert manifest["files"] == []
    assert "non-commercial" in manifest["refused"][0]["reason"]
    assert not any(url.startswith(mod.DS_SERVER) for url in calls)
    assert not (tmp_path / "items.jsonl").exists()
    assert (tmp_path / "manifest.json").exists()
