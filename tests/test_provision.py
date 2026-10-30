"""Container data provisioning (provision.py): parallel ranged downloads hashed in order, the retry
rule, stopping, files already present, and the stand-in index used with the dense artifacts."""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import urllib.error
from pathlib import Path

import pytest

from archive_debugger import provision
from archive_debugger.retrieve import dense


class FakeSource:
    """An in-memory R2: objects by key, optional failures per (key, start), a delay per read."""

    def __init__(self, objects: dict, failures: dict | None = None, delay: float = 0.0):
        self.objects = objects
        self.failures = dict(failures or {})
        self.delay = delay
        self.reads = 0
        self.lock = threading.Lock()

    def size(self, key: str) -> int:
        return len(self.objects[key])

    def read(self, key: str, start: int, end: int) -> bytes:
        with self.lock:
            self.reads += 1
            pending = self.failures.get((key, start))
            if pending:
                self.failures[(key, start)] = pending[1:]
                raise pending[0]
        if self.delay:
            threading.Event().wait(self.delay)
        return self.objects[key][start:end]


def _job(tmp_path, key: str, data: bytes, kind: str = "db") -> provision.Job:
    return provision.Job("pilot", kind, key, tmp_path / "out" / key.replace("/", "_"), hashlib.sha256(data).hexdigest())


def test_parallel_ranged_fetch_hashes_in_order(tmp_path):
    a = os.urandom(1_000_003)                        # parts do not divide it evenly
    b = os.urandom(250_000)
    jobs = [_job(tmp_path, "pilot/a.db", a), _job(tmp_path, "pilot/b.db", b, kind="index")]
    source = FakeSource({"pilot/a.db": a, "pilot/b.db": b})
    progress = provision.Progress()
    provision.fetch_all(jobs, source, progress, workers=8, part_size=65_536, stop=threading.Event(), log=lambda _m: None)
    assert jobs[0].dest.read_bytes() == a and jobs[1].dest.read_bytes() == b
    assert not list((tmp_path / "out").glob("*.part"))
    snap = progress.snapshot()
    assert snap["bytes_total"] == snap["bytes_downloaded"] == snap["bytes_verified"] == len(a) + len(b)
    assert source.reads == -(-len(a) // 65_536) + -(-len(b) // 65_536)


def test_hash_mismatch_removes_the_file_and_fails(tmp_path):
    data = os.urandom(100_000)
    job = provision.Job("pilot", "db", "pilot/x.db", tmp_path / "x.db", "0" * 64)
    with pytest.raises(provision.ProvisionError, match="sha256 mismatch"):
        provision.fetch_all([job], FakeSource({"pilot/x.db": data}), provision.Progress(), workers=4,
                            part_size=16_384, stop=threading.Event(), log=lambda _m: None)
    assert not job.dest.exists() and not (tmp_path / "x.db.part").exists()


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://r2.internal/k", code, "error", {}, io.BytesIO(b""))


def test_retry_rule(monkeypatch):
    """Timeouts, connection errors, 5xx, 408 and 429 are retried with backoff; another 4xx raises at
    once; the last failure is reported when the attempts run out."""
    stop = threading.Event()
    waits = []
    monkeypatch.setattr(stop, "wait", lambda seconds: waits.append(seconds))

    def failing(errors, result=b"ok"):
        remaining = list(errors)

        def call():
            if remaining:
                raise remaining.pop(0)
            return result
        return call

    retried = [_http_error(503), _http_error(429), _http_error(408), TimeoutError(), ConnectionError()]
    assert provision._retrying(failing(retried), "read", stop) == b"ok"
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0]
    calls = []

    def forbidden():
        calls.append(1)
        raise _http_error(403)
    with pytest.raises(provision.ProvisionError, match="HTTP 403"):
        provision._retrying(forbidden, "read", stop)
    assert calls == [1]
    monkeypatch.setattr(provision, "MAX_ATTEMPTS", 2)
    with pytest.raises(provision.ProvisionError, match="gave up after 2 attempts"):
        provision._retrying(failing([_http_error(500)] * 5), "read", stop)


def test_stop_aborts_a_download(tmp_path):
    data = os.urandom(400_000)
    job = _job(tmp_path, "pilot/s.db", data)
    stop = threading.Event()
    source = FakeSource({"pilot/s.db": data}, delay=0.05)
    threading.Timer(0.1, stop.set).start()
    with pytest.raises(provision.Stopped):
        provision.fetch_all([job], source, provision.Progress(), workers=2, part_size=8_192, stop=stop, log=lambda _m: None)
    assert not job.dest.exists()


def test_http_range_source_sends_range_and_checks_length(monkeypatch):
    data = os.urandom(1000)
    seen = []

    class Response(io.BytesIO):
        def __init__(self, body, headers):
            super().__init__(body)
            self.headers = headers

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout):
        seen.append((req.get_method(), req.full_url, req.headers.get("Range")))
        if req.get_method() == "HEAD":
            return Response(b"", {"Content-Length": str(len(data))})
        first, last = req.headers["Range"].split("=")[1].split("-")
        return Response(data[int(first):int(last) + 1], {})

    monkeypatch.setattr(provision.urllib.request, "urlopen", fake_urlopen)
    source = provision.HttpRangeSource("http://r2.internal/")
    assert source.size("pilot/civic.db") == 1000
    assert source.read("pilot/civic.db", 100, 300) == data[100:300]
    assert seen[1] == ("GET", "http://r2.internal/pilot/civic.db", "bytes=100-299")


def _registry(tmp_path, db: bytes, index: bytes, artifacts: dict | None = None) -> dict:
    entry = {"r2": {"db_key": "pilot/civic.db", "index_key": "pilot/vectors.db",
                    "db_sha256": hashlib.sha256(db).hexdigest(), "index_sha256": hashlib.sha256(index).hexdigest()}}
    if artifacts:
        entry["dense"] = {f"{part}_key": f"pilot/dense/vectors.{part}" for part in ("matrix", "ids", "manifest")}
        entry["dense"].update({f"{part}_sha256": hashlib.sha256(body).hexdigest() for part, body in artifacts.items()})
    return {"default": "pilot", "scopes": {"pilot": entry}}


def test_provision_downloads_then_verifies_present_files(tmp_path, monkeypatch):
    db, index = os.urandom(70_000), os.urandom(30_000)
    monkeypatch.setenv("CIVIC_DB_PATH", str(tmp_path / "data" / "civic.db"))
    monkeypatch.setenv("CIVIC_INDEX_PATH", str(tmp_path / "data" / "index" / "vectors.db"))
    monkeypatch.setenv("CIVIC_DENSE_BACKEND", "sqlite")
    monkeypatch.setenv(provision.ENV_PART_MB, "1")
    registry = _registry(tmp_path, db, index)
    source = FakeSource({"pilot/civic.db": db, "pilot/vectors.db": index})
    progress = provision.Progress()
    provision.provision(["pilot"], progress, stop=threading.Event(), registry=registry, source=source,
                        mode="r2-binding", log=lambda _m: None)
    assert (tmp_path / "data" / "civic.db").read_bytes() == db
    assert progress.snapshot()["stage"] == "provisioned"
    reads = source.reads
    provision.provision(["pilot"], provision.Progress(), stop=threading.Event(), registry=registry, source=source,
                        mode="r2-binding", log=lambda _m: None)
    assert source.reads == reads                                              # present and verified: nothing fetched
    (tmp_path / "data" / "civic.db").write_bytes(b"tampered")
    with pytest.raises(provision.ProvisionError, match="does not match"):
        provision.provision(["pilot"], provision.Progress(), stop=threading.Event(), registry=registry,
                            source=source, mode="r2-binding", log=lambda _m: None)
    monkeypatch.setenv(provision.ENV_VERIFY_PRESENT, "trust-image")
    provision.provision(["pilot"], provision.Progress(), stop=threading.Event(), registry=registry, source=source,
                        mode="present", log=lambda _m: None)                  # image data: trusted by digest
    monkeypatch.setenv(provision.ENV_VERIFY_PRESENT, "trust-snapshot")
    provision.provision(["pilot"], provision.Progress(), stop=threading.Event(), registry=registry, source=source,
                        mode="present", log=lambda _m: None)                  # restored disk: verified when snapshotted
    monkeypatch.setenv(provision.ENV_VERIFY_PRESENT, "trust-anything")
    with pytest.raises(provision.ProvisionError, match="unknown"):
        provision.provision(["pilot"], provision.Progress(), stop=threading.Event(), registry=registry,
                            source=source, mode="present", log=lambda _m: None)


def test_numpy_backend_fetches_artifacts_and_writes_a_stand_in_index(tmp_path, monkeypatch):
    db, index = os.urandom(20_000), os.urandom(10_000)
    manifest = json.dumps({"artifact_version": dense.ARTIFACT_VERSION, "rows": 1, "dim": 2, "index_file": "vectors.db",
                           "index_sha256": hashlib.sha256(index).hexdigest(), "index_bytes": len(index)}).encode()
    artifacts = {"matrix": b"m" * 100, "ids": b"i" * 50, "manifest": manifest}
    monkeypatch.setenv("CIVIC_DB_PATH", str(tmp_path / "data" / "civic.db"))
    monkeypatch.setenv("CIVIC_INDEX_PATH", str(tmp_path / "data" / "index" / "vectors.db"))
    monkeypatch.setenv("CIVIC_DENSE_BACKEND", "numpy")
    objects = {"pilot/civic.db": db}
    objects.update({f"pilot/dense/vectors.{part}": body for part, body in artifacts.items()})
    source = FakeSource(objects)
    provision.provision(["pilot"], provision.Progress(), stop=threading.Event(),
                        registry=_registry(tmp_path, db, index, artifacts), source=source, mode="r2-binding",
                        log=lambda _m: None)
    index_file = tmp_path / "data" / "index" / "vectors.db"
    assert "pilot/vectors.db" not in [k for k in objects]                     # the full index is never fetched
    assert dense.stub_target(index_file) == hashlib.sha256(index).hexdigest()
    paths = dense.artifact_paths(index_file)
    assert paths["matrix"].read_bytes() == artifacts["matrix"]
    assert dense.usable_artifacts(index_file) is not None                    # the stand-in is accepted for its index
    dense.stub_sidecar(index_file).write_text(json.dumps({"stands_in_for_index_sha256": "f" * 64}), encoding="utf-8")
    assert dense.usable_artifacts(index_file) is None                        # but not for another one
