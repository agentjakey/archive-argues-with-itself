"""Boot provisioning: R2 download/verify/skip/fail-fast, source selection with the github_release
fallback, enabled-scope gating, and spec building. Hermetic: a stub S3 client, temp files, no
boto3 and no network (N1). The github_release primitives themselves are covered in test_data_release."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from archive_debugger import boot, data_release as dr, scopes


def _spec(tmp_path, scope, kind, data, *, source="r2", key=None, base=None, sha=None):
    dest = tmp_path / scope / f"{kind}.db"
    return boot.FileSpec(
        scope=scope, kind=kind, dest=dest,
        sha256=hashlib.sha256(data).hexdigest() if sha is None else sha,
        source=source, r2_key=key or f"{scope}/{kind}.db",
        release_base_url=base, release_asset=dest.name,
    )


class _NotFound(Exception):
    def __init__(self, code="NoSuchKey"):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    """Minimal S3 stand-in: download_file writes the stored bytes, or raises a not-found error."""

    def __init__(self, objects):
        self.objects = dict(objects)          # {key: bytes}
        self.calls: list = []

    def download_file(self, bucket, key, filename, Callback=None):
        self.calls.append(key)
        if key not in self.objects:
            raise _NotFound()
        data = self.objects[key]
        Path(filename).write_bytes(data)
        if Callback:
            Callback(len(data))


def _r2_env(monkeypatch):
    for v in boot.R2_ENV:
        monkeypatch.setenv(v, "x")


def _no_r2_env(monkeypatch):
    for v in boot.R2_ENV:
        monkeypatch.delenv(v, raising=False)


def test_download_verifies_and_renames(tmp_path, monkeypatch):
    _r2_env(monkeypatch)
    data = os.urandom(4096)
    spec = _spec(tmp_path, "pilot", "civic", data, key="pilot/civic.db")
    client = FakeS3({"pilot/civic.db": data})
    boot._download_r2(spec, client, "bucket", lambda _m: None)
    assert spec.dest.read_bytes() == data
    assert not spec.dest.with_name(spec.dest.name + ".part").exists()


def test_download_checksum_mismatch_fails_and_removes(tmp_path, monkeypatch):
    _r2_env(monkeypatch)
    spec = _spec(tmp_path, "pilot", "civic", os.urandom(1024), key="pilot/civic.db")
    client = FakeS3({"pilot/civic.db": os.urandom(1024)})   # different bytes -> hash mismatch
    with pytest.raises(boot.BootError) as e:
        boot._download_r2(spec, client, "bucket", lambda _m: None)
    assert "pilot/civic" in str(e.value) and "mismatch" in str(e.value).lower()
    assert not spec.dest.exists()
    assert not spec.dest.with_name(spec.dest.name + ".part").exists()


def test_download_missing_object_fails_loud_naming_scope_and_key(tmp_path, monkeypatch):
    _r2_env(monkeypatch)
    spec = _spec(tmp_path, "microlog", "civic", os.urandom(512), key="microlog/civic_microlog.db")
    with pytest.raises(boot.BootError) as e:
        boot._download_r2(spec, FakeS3({}), "bucket", lambda _m: None)
    msg = str(e.value)
    assert "microlog/civic" in msg and "not found" in msg.lower() and "microlog/civic_microlog.db" in msg


def test_provision_skips_when_present_and_current(tmp_path, monkeypatch):
    _r2_env(monkeypatch)
    data = os.urandom(4096)
    spec = _spec(tmp_path, "pilot", "civic", data, key="pilot/civic.db")
    spec.dest.parent.mkdir(parents=True)
    spec.dest.write_bytes(data)                              # already present with the right hash
    client = FakeS3({"pilot/civic.db": data})
    boot.provision_scope([spec], lambda _m: None, get_client=lambda: client)
    assert client.calls == []                               # idempotent: no download attempted


def test_provision_downloads_both_files_when_absent(tmp_path, monkeypatch):
    _r2_env(monkeypatch)
    d1, d2 = os.urandom(2048), os.urandom(2048)
    s1 = _spec(tmp_path, "microlog", "civic", d1, key="microlog/civic_microlog.db")
    s2 = _spec(tmp_path, "microlog", "index", d2, key="microlog/vectors_microlog.db")
    client = FakeS3({"microlog/civic_microlog.db": d1, "microlog/vectors_microlog.db": d2})
    boot.provision_scope([s1, s2], lambda _m: None, get_client=lambda: client)
    assert s1.dest.read_bytes() == d1 and s2.dest.read_bytes() == d2
    assert set(client.calls) == {"microlog/civic_microlog.db", "microlog/vectors_microlog.db"}


def test_missing_creds_no_fallback_fails_fast(tmp_path, monkeypatch):
    _no_r2_env(monkeypatch)
    spec = _spec(tmp_path, "microlog", "civic", os.urandom(256), key="microlog/civic_microlog.db", base=None)
    with pytest.raises(boot.BootError) as e:                # r2 selected, creds absent, no fallback, file absent
        boot.provision_scope([spec], lambda _m: None, get_client=boot.make_r2_client)
    assert "microlog" in str(e.value) and "missing: civic" in str(e.value)


def test_missing_creds_but_file_present_is_ok(tmp_path, monkeypatch):
    _no_r2_env(monkeypatch)
    data = os.urandom(1024)
    spec = _spec(tmp_path, "microlog", "civic", data, base=None)
    spec.dest.parent.mkdir(parents=True)
    spec.dest.write_bytes(data)                             # offline restart: data already on the volume
    boot.provision_scope([spec], lambda _m: None, get_client=boot.make_r2_client)   # no raise


def test_r2_absent_falls_back_to_github_release(tmp_path, monkeypatch):
    """Pilot shape: source=r2 but R2 vars absent -> the github_release fallback provisions it."""
    _no_r2_env(monkeypatch)
    data = os.urandom(4096)
    src = tmp_path / "release"
    src.mkdir()
    (src / "civic.db").write_bytes(data)
    dr.write_checksums({"civic.db": src / "civic.db"}, src / dr.CHECKSUM_FILE, log=lambda _m: None)
    dest = tmp_path / "data" / "civic.db"
    spec = boot.FileSpec(scope="pilot", kind="db", dest=dest, sha256="", source="r2",
                         r2_key="pilot/civic.db", release_base_url=src.resolve().as_uri(),
                         release_asset="civic.db")

    def _no_client():
        raise AssertionError("R2 client must not be built when falling back to github_release")

    boot.provision_scope([spec], lambda _m: None, get_client=_no_client)
    assert dest.read_bytes() == data


def test_enabled_for_boot_default_always_included_and_gates():
    reg = {"default": "pilot", "scopes": {"pilot": {}, "microlog": {}, "education": {}}}
    assert boot.enabled_for_boot(reg, None) == ["pilot"]                    # unset -> the default only
    assert boot.enabled_for_boot(reg, "pilot,microlog") == ["pilot", "microlog"]
    assert boot.enabled_for_boot(reg, "microlog") == ["pilot", "microlog"]  # default always provisioned
    assert boot.enabled_for_boot(reg, "education,microlog") == ["pilot", "education", "microlog"]


def test_scope_provision_specs_reads_source_keys_hashes_and_dest(tmp_path, monkeypatch):
    reg = {"default": "pilot", "scopes": {"microlog": {
        "source": "r2",
        "r2": {"db_key": "microlog/civic_microlog.db", "index_key": "microlog/vectors_microlog.db",
               "db_sha256": "a" * 64, "index_sha256": "b" * 64}}}}
    fake = scopes.Scope(name="microlog", config_path=Path("config/microlog.toml"),
                        db_path=tmp_path / "m" / "civic_microlog.db",
                        index_path=tmp_path / "m" / "vectors_microlog.db",
                        cache_dir=Path("raw"), inherit=False)
    monkeypatch.setattr(scopes, "resolve_scope", lambda name, **k: fake)
    specs = boot.scope_provision_specs("microlog", registry=reg)
    assert [s.kind for s in specs] == ["db", "index"]
    assert specs[0].r2_key == "microlog/civic_microlog.db" and specs[0].sha256 == "a" * 64
    assert specs[0].dest == fake.db_path
    assert specs[1].r2_key == "microlog/vectors_microlog.db" and specs[1].sha256 == "b" * 64
    assert specs[1].dest == fake.index_path


def test_scope_provision_specs_requires_valid_hash_for_r2(tmp_path, monkeypatch):
    reg = {"default": "pilot", "scopes": {"microlog": {"source": "r2", "r2": {"db_key": "k"}}}}
    fake = scopes.Scope(name="microlog", config_path=Path("x"), db_path=tmp_path / "a",
                        index_path=tmp_path / "b", cache_dir=Path("raw"), inherit=False)
    monkeypatch.setattr(scopes, "resolve_scope", lambda name, **k: fake)
    with pytest.raises(boot.BootError):
        boot.scope_provision_specs("microlog", registry=reg)
