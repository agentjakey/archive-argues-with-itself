"""The cloud fetch and build (GitHub Actions): the concurrency ceiling, Retry-After, streaming to R2
with nothing kept on disk, a clean stop at the time budget, and the shard release gates."""
from __future__ import annotations

import gzip
import importlib.util
import json
import socket
import urllib.error
from pathlib import Path

import pytest

from archive_debugger.catalogue import fulltext, net

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_no_run_may_send_more_than_eight_requests_at_once():
    with pytest.raises(ValueError):
        net.AdaptiveLimit(start=4, ceiling=9)
    with pytest.raises(ValueError):
        net.configure(9, 9)
    clock = Clock()
    lim = net.AdaptiveLimit(start=4, ceiling=8, step=2, quiet_s=3600, window_s=900, min_samples=5, clock=clock)
    for minute in range(61):
        clock.t = minute * 60
        lim.observe(0.5)
    assert lim.limit == 6                        # one quiet, flat hour: one step of two
    for minute in range(61, 122):
        clock.t = minute * 60
        lim.observe(0.5)
    assert lim.limit == 8
    for minute in range(122, 250):
        clock.t = minute * 60
        lim.observe(0.5)
    assert lim.limit == 8                        # never above the ceiling
    lim.problem("HTTP 429")
    assert lim.limit == 4


def test_retry_after_is_honoured_in_full_and_pauses_every_request(monkeypatch):
    assert net.retry_after_s("120") == 120.0 and net.retry_after_s(None) is None
    assert net.retry_after_s("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0      # a date in the past: no wait
    slept = []
    lim = net.AdaptiveLimit(start=4, ceiling=8)
    calls = {"n": 0}

    class Headers(dict):
        def get(self, key, default=None):
            return super().get(key.lower(), default)

    def urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", Headers({"retry-after": "300"}), None)

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"ok"
        return Resp()
    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lim, "acquire", lambda: None)          # the hold itself is checked below
    assert net.get("https://archive.org/x", sleep=slept.append, limit=lim) == b"ok"
    assert slept[0] == 300.0                                      # not cut to the backoff cap
    assert lim.hold_until > lim.clock() + 200                    # every other request waits too
    calls["n"] = 0

    def far(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "busy", Headers({"retry-after": "7200"}), None)
    monkeypatch.setattr(net.urllib.request, "urlopen", far)
    with pytest.raises(net.TooManyRefusals):
        net.get("https://archive.org/x", sleep=slept.append, limit=lim)


def served_get(served):
    def get(url, refusals=None):
        name = url.rsplit("/", 1)[-1]
        if name in served:
            return served[name]
        raise net.HttpError(404, "missing")
    return get


def test_streaming_keeps_nothing_but_the_manifest_and_writes_status_to_r2(tmp_path):
    from archive_debugger.jobs.store import LocalStore
    store = LocalStore(tmp_path / "r2")
    served = {f"item{i}_hocr_searchtext.txt.gz": gzip.compress(b"text") for i in range(3)}
    fulltext.run([f"item{i}" for i in range(3)], tmp_path / "runner", store=store, get=served_get(served),
                 log=lambda m: None, keep_local=False, runner="actions run 1")
    assert sorted(p.name for p in (tmp_path / "runner").iterdir()) == ["manifest.jsonl", "manifest.synced", "status.json"]
    assert store.get("fulltext/v1/item0/item0_hocr_searchtext.txt.gz") == served["item0_hocr_searchtext.txt.gz"]
    status = json.loads(store.get(fulltext.STATUS_KEY))
    assert status["done"] == 3 and status["runner"] == "actions run 1"


def test_a_run_past_its_time_budget_starts_nothing_new_and_syncs(tmp_path):
    from archive_debugger.jobs.store import LocalStore
    store = LocalStore(tmp_path / "r2")
    served = {f"item{i}_hocr_searchtext.txt.gz": gzip.compress(b"text") for i in range(3)}
    counts = fulltext.run([f"item{i}" for i in range(3)], tmp_path / "runner", store=store, get=served_get(served),
                          log=lambda m: None, keep_local=False, deadline=0.0)
    assert counts["out_of_time"] and counts["fetched"] == 0 and not counts["stopped"]


def builder():
    spec = importlib.util.spec_from_file_location("shard_builder", REPO / "scripts" / "v2" / "shard_builder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_shard_that_fails_a_release_gate_is_never_uploaded(tmp_path):
    from archive_debugger.ingest import db as ingest_db
    from archive_debugger.jobs import compile as comp
    sb = builder()
    text = "Annual report of the hospital board, with figures on beds and patients admitted this year"
    files = {"searchtext": gzip.compress(text.encode()),
             "pageindex": gzip.compress(json.dumps([[0, len(text), 0, 0]]).encode()),
             "page_numbers": gzip.compress(json.dumps({"pages": [{"leafNum": 0, "pageNumber": "1"}]}).encode())}
    unit = gzip.compress("".join(json.dumps(l) + "\n" for l in comp.compile_item(
        "itema", files, {"title": "t"}, target_tokens=300, overlap_tokens=40)).encode())
    counts = comp.pack_shard([unit], tmp_path / "civic.db", init_db=ingest_db.init_db)
    assert sb.gates(tmp_path / "civic.db", ["itema"], counts) == []
    # A document of the plan that is neither built nor reported skipped fails the gate.
    assert any("documents" in f for f in sb.gates(tmp_path / "civic.db", ["itema", "itemb"], counts))
    # So does an item that is not in the shard's plan.
    assert any("not in the shard's plan" in f for f in sb.gates(tmp_path / "civic.db", ["itemz"], {**counts, "skipped": 0}))
