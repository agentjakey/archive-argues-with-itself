"""Server lifecycle: the port answers while the data is provisioned and the scopes open, readiness
comes before warming, and shutdown at any stage stops background work before closing anything
(known error 8). A subprocess test sends SIGTERM at each stage on Linux, where containers run."""
from __future__ import annotations

import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archive_debugger import provision
from archive_debugger.api import app as app_module

REPO = Path(__file__).resolve().parent.parent
SLOW_SQL = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c LIMIT 2000000000) "
            "SELECT COUNT(*) FROM c")


def _fixture(tmp_path) -> Path:
    spec = importlib.util.spec_from_file_location("make_fixture_db", REPO / "scripts" / "make_fixture_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main([str(tmp_path / "data")]) == 0
    return tmp_path / "data"


@pytest.fixture
def fixture_env(tmp_path, monkeypatch):
    data = _fixture(tmp_path)
    monkeypatch.setenv("CIVIC_DB_PATH", str(data / "civic.db"))
    monkeypatch.setenv("CIVIC_INDEX_PATH", str(data / "vectors.db"))
    monkeypatch.setenv("CIVIC_EMBEDDER", "stub")
    monkeypatch.setenv("CIVIC_ENABLED_SCOPES", "pilot")
    monkeypatch.delenv(provision.ENV_PROVISION, raising=False)
    monkeypatch.setattr(app_module, "_prime_model_client", lambda: None)
    return data


def _app(tmp_path):
    return app_module.create_app(Path("config/pilot.toml"), load_env=False, web_dist=tmp_path / "nodist",
                                 cache_path=tmp_path / "cache" / "answers.db")


def test_port_answers_while_starting_then_ready_before_warm(tmp_path, fixture_env, monkeypatch):
    release = threading.Event()
    warm_started = threading.Event()

    def slow_provision(names, progress, *, stop, **_kw):
        progress.set_stage("downloading")
        progress.add_file("pilot/db", 100)
        progress.advance("pilot/db", downloaded=40)
        while not release.is_set():
            if stop.wait(0.05):
                raise provision.Stopped("test")

    def slow_warm(conn, *, vectors=True):
        warm_started.set()
        try:
            conn.execute(SLOW_SQL).fetchone()      # runs until shutdown interrupts it
        except Exception:  # noqa: BLE001 - the interrupt is the expected end
            pass

    monkeypatch.setenv(provision.ENV_PROVISION, "present")
    monkeypatch.setattr(provision, "provision", slow_provision)
    monkeypatch.setattr(app_module, "_warm", slow_warm)
    app = _app(tmp_path)
    with TestClient(app) as c:
        for _ in range(200):
            if app.state.progress.snapshot()["stage"] == "downloading":
                break
            time.sleep(0.02)
        h = c.get("/health")
        assert h.status_code == 503 and h.json()["status"] == "starting"
        assert h.json()["stage"]["stage"] == "downloading" and h.json()["stage"]["bytes_downloaded"] == 40
        a = c.post("/ask", json={"question": "vaccination"})
        assert a.status_code == 200 and a.json()["degraded"]["reason"] == "starting"
        assert a.json()["answer"]["abstained"] is True and a.json()["evidence"] == []
        s = c.get("/stories")
        assert s.status_code == 503 and s.json()["detail"]["status"] == "starting"
        release.set()
        assert app.state.ready.wait(30)
        assert warm_started.wait(30)
        h = c.get("/health")
        assert h.status_code == 200 and h.json()["ready"] is True and h.json()["warmed"] is False
        assert c.post("/ask", json={"question": "vaccination hospital", "provider": "stub"}).status_code == 200
        t0 = time.monotonic()
    assert time.monotonic() - t0 < 15                                    # shutdown interrupted the warm query
    assert not any(t.name in ("startup", "boot-warm") and t.is_alive() for t in threading.enumerate())


def test_shutdown_during_provisioning_is_clean(tmp_path, fixture_env, monkeypatch):
    entered = threading.Event()

    def endless(names, progress, *, stop, **_kw):
        entered.set()
        while not stop.wait(0.05):
            pass
        raise provision.Stopped("test")

    monkeypatch.setenv(provision.ENV_PROVISION, "present")
    monkeypatch.setattr(provision, "provision", endless)
    app = _app(tmp_path)
    with TestClient(app):
        assert entered.wait(10)
    assert not app.state.ready.is_set() and app.state.startup_error is None


def test_failed_start_is_reported_not_crashed(tmp_path, fixture_env, monkeypatch):
    def broken(names, progress, *, stop, **_kw):
        raise provision.ProvisionError("pilot/db: sha256 mismatch")

    monkeypatch.setenv(provision.ENV_PROVISION, "present")
    monkeypatch.setattr(provision, "provision", broken)
    app = _app(tmp_path)
    with TestClient(app) as c:
        for _ in range(100):
            if app.state.startup_error:
                break
            time.sleep(0.05)
        h = c.get("/health")
        assert h.status_code == 503 and h.json()["status"] == "failed" and "sha256 mismatch" in h.json()["error"]
        assert c.post("/ask", json={"question": "q"}).json()["degraded"]["reason"] == "starting"


def test_stand_in_index_without_artifacts_never_answers(tmp_path, fixture_env, monkeypatch):
    """With the boot's stand-in index but no loadable dense artifacts, a scope must not answer from
    BM25 alone: it shows limited mode."""
    stand_in = tmp_path / "stand-in" / "vectors.db"
    provision.write_stub_index(stand_in, "a" * 64)
    monkeypatch.setenv("CIVIC_INDEX_PATH", str(stand_in))
    monkeypatch.setenv("CIVIC_DENSE_BACKEND", "numpy")
    app = _app(tmp_path)
    with TestClient(app) as c:
        assert app.state.ready.wait(30)
        assert c.get("/health").json()["answers"] is False
        j = c.post("/ask", json={"question": "vaccination hospital", "provider": "stub"}).json()
        assert j["degraded"]["reason"] == "index_unavailable" and j["answer"]["cached"] is None


# --- SIGTERM in a real process --------------------------------------------------------------------

SERVER = """
import os, sys, threading
sys.path.insert(0, {src!r})
from archive_debugger import provision
from archive_debugger.api import app as app_module
stage = os.environ["TEST_STAGE"]
def endless(names, progress, *, stop, **kw):
    progress.set_stage("downloading")
    print("STAGE provisioning", flush=True)
    while not stop.wait(0.05):
        pass
    raise provision.Stopped("sigterm")
def slow_warm(conn, *, vectors=True):
    print("STAGE warming", flush=True)
    try:
        conn.execute({sql!r}).fetchone()
    except Exception:
        pass
if stage == "provisioning":
    os.environ[provision.ENV_PROVISION] = "present"
    provision.provision = endless
if stage == "warming":
    app_module._warm = slow_warm
app_module._prime_model_client = lambda: None
import uvicorn
app = app_module.create_app(load_env=False)
def report_ready():
    if app.state.ready.wait(60):
        print("STAGE ready", flush=True)
threading.Thread(target=lambda: (__import__("time").sleep(0.5), report_ready()), daemon=True).start()
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["TEST_PORT"]), log_level="warning")

"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM handling is tested on Linux, where the container runs")
@pytest.mark.parametrize("stage", ["provisioning", "warming", "ready"])
def test_sigterm_at_each_stage_exits_cleanly(tmp_path, fixture_env, stage):
    script = tmp_path / "server.py"
    script.write_text(SERVER.format(src=str(REPO / "src"), sql=SLOW_SQL), encoding="utf-8")
    env = dict(os.environ, TEST_STAGE=stage, TEST_PORT=str(_free_port()))
    proc = subprocess.Popen([sys.executable, str(script)], cwd=REPO, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    want = {"provisioning": "STAGE provisioning", "warming": "STAGE warming", "ready": "STAGE ready"}[stage]
    seen = []
    deadline = time.monotonic() + 60
    for line in proc.stdout:
        seen.append(line.rstrip())
        if want in line or time.monotonic() > deadline:
            break
    assert want in "\n".join(seen), seen
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=30)
    seen += out.splitlines()
    text = "\n".join(seen)
    # uvicorn shuts down gracefully, then re-raises the captured SIGTERM, so the exit status is
    # -SIGTERM (or 0 on older versions). A crash would show a traceback or another signal.
    assert proc.returncode in (0, -signal.SIGTERM), seen
    assert "[shutdown] stopped cleanly" in text and "Traceback" not in text, seen
