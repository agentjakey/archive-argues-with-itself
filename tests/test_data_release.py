"""Data release: checksum format, resumable download against a Range-capable local
server, boot-time verify/skip/re-download, file:// URLs, and the release script."""
from __future__ import annotations

import hashlib
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from archive_debugger import data_release as dr


class _RangeServer:
    """Serves a directory with HTTP Range support; `ignore_range` makes it answer 200 always."""

    def __init__(self, root: Path, ignore_range: bool = False):
        root = Path(root)
        ignore = ignore_range

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_GET(self):
                path = root / self.path.lstrip("/")
                if not path.is_file():
                    self.send_response(404)
                    self.end_headers()
                    return
                data = path.read_bytes()
                rng = self.headers.get("Range")
                if rng and not ignore:
                    start = int(rng.split("=")[1].split("-")[0])
                    if start >= len(data):
                        self.send_response(416)
                        self.end_headers()
                        return
                    body = data[start:]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    body = data
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def _release(tmp_path: Path) -> tuple[Path, dict]:
    src = tmp_path / "release"
    src.mkdir()
    files = {"civic.db": src / "civic.db", "vectors.db": src / "vectors.db"}
    files["civic.db"].write_bytes(os.urandom(300_000))
    files["vectors.db"].write_bytes(os.urandom(120_000))
    dr.write_checksums(files, src / dr.CHECKSUM_FILE, log=lambda _m: None)
    return src, files


def test_checksum_format_roundtrip(tmp_path):
    src, files = _release(tmp_path)
    text = (src / dr.CHECKSUM_FILE).read_text(encoding="utf-8")
    parsed = dr.parse_checksums(text)
    assert set(parsed) == {"civic.db", "vectors.db"}
    assert parsed["civic.db"] == hashlib.sha256(files["civic.db"].read_bytes()).hexdigest()
    assert all(len(v) == 64 for v in parsed.values()) and "  civic.db" in text     # sha256sum -c compatible
    with pytest.raises(ValueError):
        dr.parse_checksums("nonsense line\n")


def test_ensure_data_downloads_verifies_and_skips(tmp_path):
    src, files = _release(tmp_path)
    srv = _RangeServer(src)
    try:
        dest = {"civic.db": tmp_path / "data" / "civic.db", "vectors.db": tmp_path / "data" / "index" / "vectors.db"}
        logs = []
        out = dr.ensure_data(dest, srv.url, logs.append)
        assert out == {"civic.db": "downloaded", "vectors.db": "downloaded"}
        assert dest["civic.db"].read_bytes() == files["civic.db"].read_bytes()
        assert not any(p.suffix == ".part" for p in (tmp_path / "data").rglob("*"))
        out = dr.ensure_data(dest, srv.url, logs.append)                    # second boot: verified, no download
        assert out == {"civic.db": "verified", "vectors.db": "verified"}
        dest["vectors.db"].write_bytes(b"corrupt")                          # tampered file is replaced
        out = dr.ensure_data(dest, srv.url, logs.append)
        assert out["vectors.db"] == "downloaded" and dest["vectors.db"].read_bytes() == files["vectors.db"].read_bytes()
    finally:
        srv.close()


def test_download_resumes_partial_file(tmp_path):
    src, files = _release(tmp_path)
    srv = _RangeServer(src)
    try:
        dest = tmp_path / "out" / "civic.db"
        dest.parent.mkdir()
        part = dest.with_name("civic.db.part")
        part.write_bytes(files["civic.db"].read_bytes()[:100_000])          # interrupted earlier download
        logs = []
        dr.download(f"{srv.url}/civic.db", dest, logs.append)
        assert dest.read_bytes() == files["civic.db"].read_bytes() and not part.exists()
        assert any("resuming at" in m for m in logs)
    finally:
        srv.close()


def test_download_restarts_when_server_ignores_range(tmp_path):
    src, files = _release(tmp_path)
    srv = _RangeServer(src, ignore_range=True)
    try:
        dest = tmp_path / "out" / "civic.db"
        dest.parent.mkdir()
        dest.with_name("civic.db.part").write_bytes(b"garbage")
        logs = []
        dr.download(f"{srv.url}/civic.db", dest, logs.append)
        assert dest.read_bytes() == files["civic.db"].read_bytes()
        assert any("starting over" in m for m in logs)
    finally:
        srv.close()


def test_checksum_mismatch_removes_download(tmp_path):
    src, files = _release(tmp_path)
    (src / dr.CHECKSUM_FILE).write_text("0" * 64 + "  civic.db\n" + "0" * 64 + "  vectors.db\n", encoding="utf-8")
    srv = _RangeServer(src)
    try:
        dest = {"civic.db": tmp_path / "d" / "civic.db", "vectors.db": tmp_path / "d" / "vectors.db"}
        with pytest.raises(dr.ChecksumMismatch):
            dr.ensure_data(dest, srv.url, lambda _m: None)
        assert not dest["civic.db"].exists()
    finally:
        srv.close()


def test_file_url_and_no_url_paths(tmp_path):
    src, files = _release(tmp_path)
    dest = {"civic.db": tmp_path / "d" / "civic.db", "vectors.db": tmp_path / "d" / "vectors.db"}
    out = dr.ensure_data(dest, src.resolve().as_uri(), lambda _m: None)      # file:// base URL
    assert out == {"civic.db": "downloaded", "vectors.db": "downloaded"}
    assert dr.ensure_data(dest, None, lambda _m: None) == {"civic.db": "present-unverified", "vectors.db": "present-unverified"}
    with pytest.raises(FileNotFoundError):
        dr.ensure_data({"civic.db": tmp_path / "nowhere.db"}, None, lambda _m: None)


def test_make_data_release_script_prints_gh_command(tmp_path, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("mdr", Path("scripts/make_data_release.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src, files = _release(tmp_path)
    out = tmp_path / "data-release.sha256"
    rc = mod.main(["--db", str(files["civic.db"]), "--index", str(files["vectors.db"]), "--out", str(out), "--tag", "data-v9"])
    text = capsys.readouterr().out
    assert rc == 0 and out.exists()
    assert "gh release create data-v9" in text and "#civic.db" in text and "#vectors.db" in text
    assert "DATA_RELEASE_URL=https://github.com/agentjakey/archive-argues-with-itself/releases/download/data-v9" in text
