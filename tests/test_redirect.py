"""The Railway redirect app answers every request with a 301 to the same path and query on the
new domain, maps the paths that moved, and runs as a real HTTP server."""
from __future__ import annotations

import http.client
import importlib.util
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("redirect_app", REPO / "redirect" / "redirect_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_targets_keep_path_and_query():
    mod = _module()
    t = "https://archiveargues.org"
    assert mod.target_for("/", t) == "https://archiveargues.org/"
    assert mod.target_for("/?view=gaps&scope=microlog", t) == "https://archiveargues.org/?view=gaps&scope=microlog"
    assert mod.target_for("/og-image.png", t) == "https://archiveargues.org/og-image.png"
    assert mod.target_for("/ask?q=tobacco+policy&jurisdiction=ontario", t) == \
        "https://archiveargues.org/?q=tobacco+policy&jurisdiction=ontario"
    assert mod.target_for("/health", t) == "https://api.archiveargues.org/health"
    assert mod.target_for("/assets/index.js?v=2", t) == "https://archiveargues.org/assets/index.js?v=2"


def test_server_answers_301_for_every_method():
    mod = _module()
    server = mod.make_server(0, "https://archiveargues.org")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        for method, path in (("GET", "/?q=vaccination%20hospital"), ("HEAD", "/stories"), ("POST", "/ask?q=x")):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=b"{}" if method == "POST" else None)
            resp = conn.getresponse()
            resp.read()
            assert resp.status == 301
            assert resp.getheader("Location").startswith("https://archiveargues.org/")
            conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/?q=vaccination%20hospital")
        assert conn.getresponse().getheader("Location") == "https://archiveargues.org/?q=vaccination%20hospital"
    finally:
        server.shutdown()
        server.server_close()


def test_health_path_answers_200_for_railway():
    mod = _module()
    server = mod.make_server(0, "https://archiveargues.org")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", mod.HEALTH_PATH)
        resp = conn.getresponse()
        assert resp.status == 200 and resp.read() == b"ok\n"
    finally:
        server.shutdown()
        server.server_close()
