"""Boot-time data provisioning across enabled scopes (Cloudflare R2, GitHub-release fallback).

The container runs `python -m archive_debugger.boot` before serving. For each ENABLED scope it
puts that scope's two data files (civic db + vector index) on the scope's resolved paths, from
the scope's configured source, then verifies sha256 against the value recorded in
config/scopes.toml. A file already present with the right hash is left alone (idempotent, no
re-download). Any missing R2 creds/object, or any checksum mismatch, fails the boot loudly
(non-zero) naming the scope and key -- the server never starts half-served.

Source selection (config/scopes.toml, per scope):
  source = "r2"              -> stream both objects from R2 (boto3, S3-compatible).
  source = "github_release"  -> the existing data_release flow (release checksum file).
Per file the order is: skip if already present with the expected hash; else R2 when source=r2
and the R2 vars are set; else the github_release fallback when the scope has one; else fail.
So a scope whose source is r2 but with a [github_release] block still boots the old way when the
R2 vars are absent (the pilot, whose files are under GitHub's 2 GiB per-asset cap). A scope with
no fallback (microlog, files over that cap) fails fast when R2 is unavailable and no local data
is present.

Which scopes are provisioned is CIVIC_ENABLED_SCOPES plus the always-served default scope; a
scope that is not enabled is never downloaded. N1: the only network here is R2 or the release
host; nothing touches the Internet Archive."""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from archive_debugger import scopes
from archive_debugger.data_release import ChecksumMismatch, ensure_data, sha256_file

R2_ENV = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
ENV_ENABLED_SCOPES = "CIVIC_ENABLED_SCOPES"
LOG_EVERY = 100 * 1024 * 1024

Log = Callable[[str], None]


class BootError(RuntimeError):
    """A scope could not be provisioned; the boot must exit non-zero without serving."""


@dataclass
class FileSpec:
    """One data file to provision: where it must land, its expected hash, and how to get it."""
    scope: str
    kind: str                        # "db" or "index"
    dest: Path
    sha256: str                      # expected; "" for a github_release-only scope (release-verified)
    source: str                      # "r2" or "github_release"
    r2_key: Optional[str]
    release_base_url: Optional[str]  # None when the scope has no github_release fallback
    release_asset: str               # asset name in the release (the dest basename)


def _mb(n: int) -> str:
    return f"{n / 1_000_000:,.0f} MB"


def r2_creds_present() -> bool:
    return all(os.environ.get(v) for v in R2_ENV)


def _release_base_url(name: str, entry: dict, registry: dict) -> Optional[str]:
    """The github_release base URL for a scope: its [github_release] block (base_url or url_env),
    or, for the default scope with no block, the legacy DATA_RELEASE_URL env for back-compat."""
    gh = entry.get("github_release") or {}
    if gh:
        if gh.get("base_url"):
            return str(gh["base_url"])
        if gh.get("url_env"):
            return os.environ.get(str(gh["url_env"]))
        return None
    if name == registry.get("default"):
        return os.environ.get("DATA_RELEASE_URL")
    return None


def scope_provision_specs(name: str, *, registry: Optional[dict] = None) -> list[FileSpec]:
    """The two FileSpecs (db, index) for a scope, from resolve_scope (the dest paths the serve
    layer will read) plus the registry provisioning config. Raises BootError when source=r2 but
    the registry lacks a valid expected sha256 for a file."""
    reg = registry if registry is not None else scopes.load_registry()
    entry = reg.get("scopes", {}).get(name, {}) or {}
    resolved = scopes.resolve_scope(name)
    source = str(entry.get("source") or "github_release").lower()
    r2 = entry.get("r2") or {}
    release_base = _release_base_url(name, entry, reg)

    specs: list[FileSpec] = []
    for kind, dest, key_field, sha_field in (
        ("db", resolved.db_path, "db_key", "db_sha256"),
        ("index", resolved.index_path, "index_key", "index_sha256"),
    ):
        sha = str(r2.get(sha_field) or "").lower()
        if source == "r2" and len(sha) != 64:
            raise BootError(f"[{name}/{kind}] source=r2 but no valid {sha_field} in config/scopes.toml")
        specs.append(FileSpec(
            scope=name, kind=kind, dest=Path(dest), sha256=sha, source=source,
            r2_key=r2.get(key_field), release_base_url=release_base, release_asset=Path(dest).name,
        ))
    return specs


def enabled_for_boot(registry: dict, env_value: Optional[str]) -> list[str]:
    """Scopes to provision: the always-served default plus every scope in CIVIC_ENABLED_SCOPES.
    Unset -> just the default (the single-scope deploy). A scope not enabled is never downloaded.
    Ordered default-first, then the rest sorted, for deterministic logs."""
    default = registry.get("default", "pilot")
    enabled = scopes.parse_enabled_scopes(env_value)
    names = {default} | (enabled or set())
    return [default] + sorted(n for n in names if n != default)


def _skip_if_current(spec: FileSpec, log: Log) -> bool:
    """True (skip) when the file is already present with the expected sha256. Only meaningful for
    a scope that carries an expected hash (source=r2); a github_release scope returns False here
    and lets data_release verify against the release checksum instead."""
    if not spec.sha256 or not spec.dest.exists():
        return False
    log(f"[{spec.scope}/{spec.kind}] present at {spec.dest} ({_mb(spec.dest.stat().st_size)}), verifying sha256")
    if sha256_file(spec.dest, log) == spec.sha256:
        log(f"[{spec.scope}/{spec.kind}] sha256 ok; skip, already current")
        return True
    log(f"[{spec.scope}/{spec.kind}] sha256 mismatch on disk; will re-provision")
    return False


def make_r2_client():
    """An S3 client pointed at the R2 endpoint, from the R2_* env. boto3 is imported here (not at
    module load) so this module and its tests do not require boto3 unless a real R2 download runs.
    Raises BootError on missing creds or a missing boto3."""
    missing = [v for v in R2_ENV if not os.environ.get(v)]
    if missing:
        raise BootError(f"R2 selected but missing env: {', '.join(missing)}")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise BootError(f"R2 selected but boto3 is not installed ({exc}); add it to requirements") from exc
    return boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )


def _download_r2(spec: FileSpec, client, bucket: str, log: Log) -> None:
    """Stream one object from R2 to spec.dest via a .part file, verify its sha256, then rename.
    Fails loudly (BootError) naming the scope and key on a missing object, a transport error, or a
    checksum mismatch. boto3/botocore are not imported here, so a stubbed client works in tests."""
    dest = spec.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    log(f"[{spec.scope}/{spec.kind}] downloading s3://{bucket}/{spec.r2_key} -> {dest}")

    sent = {"n": 0, "next": LOG_EVERY}
    lock = threading.Lock()

    def progress(chunk: int) -> None:
        with lock:
            sent["n"] += chunk
            if sent["n"] >= sent["next"]:
                log(f"[{spec.scope}/{spec.kind}] {_mb(sent['n'])}")
                sent["next"] += LOG_EVERY

    try:
        client.download_file(bucket, spec.r2_key, str(part), Callback=progress)
    except Exception as exc:  # noqa: BLE001 - any download error must fail the boot, loudly and named
        part.unlink(missing_ok=True)
        code = ""
        resp = getattr(exc, "response", None)
        if isinstance(resp, dict):
            code = str(resp.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound") or "not found" in str(exc).lower():
            raise BootError(f"[{spec.scope}/{spec.kind}] R2 object not found: s3://{bucket}/{spec.r2_key}") from exc
        raise BootError(f"[{spec.scope}/{spec.kind}] R2 download failed for s3://{bucket}/{spec.r2_key}: {exc}") from exc

    got = sha256_file(part, log)
    if got != spec.sha256:
        part.unlink(missing_ok=True)
        raise BootError(f"[{spec.scope}/{spec.kind}] sha256 mismatch after download (s3://{bucket}/{spec.r2_key}): "
                        f"got {got[:16]}..., expected {spec.sha256[:16]}...; removed")
    part.replace(dest)
    log(f"[{spec.scope}/{spec.kind}] downloaded + verified ({_mb(dest.stat().st_size)})")


def _provision_github_release(specs: list[FileSpec], log: Log) -> None:
    """Provision a scope's files through the existing data_release flow (verify against the
    release's data-release.sha256). One attempt: a transient failure exits the boot non-zero and
    the container restart resumes from the .part file (data_release.download resumes)."""
    scope = specs[0].scope
    base = specs[0].release_base_url
    targets = {s.release_asset: s.dest for s in specs}
    try:
        result = ensure_data(targets, base, log)
    except ChecksumMismatch as exc:
        raise BootError(f"[{scope}] github_release checksum mismatch: {exc}") from exc
    except FileNotFoundError as exc:
        raise BootError(f"[{scope}] github_release: {exc}") from exc
    except (OSError, ValueError, KeyError) as exc:
        raise BootError(f"[{scope}] github_release provisioning failed: {type(exc).__name__}: {exc}") from exc
    log(f"[{scope}] github_release: {result}")


def provision_scope(specs: list[FileSpec], log: Log, *, get_client: Callable[[], object]) -> None:
    """Provision one scope's two files. R2 (source=r2, creds present) verifies against the config
    hash; otherwise the github_release fallback runs when the scope has one; otherwise a file that
    is not already present is a fail-fast. get_client returns the R2 client lazily (created once)."""
    scope = specs[0].scope
    source = specs[0].source

    if source == "r2" and r2_creds_present():
        bucket = os.environ["R2_BUCKET"]
        for spec in specs:
            if _skip_if_current(spec, log):
                continue
            _download_r2(spec, get_client(), bucket, log)   # client built lazily, only when a download is needed
        return

    if specs[0].release_base_url or source == "github_release":
        _provision_github_release(specs, log)
        return

    # No R2 (creds absent) and no github_release fallback: a file already present with the right
    # hash is fine (offline / local); anything missing is a loud fail-fast (never serve half).
    missing = [s.kind for s in specs if not _skip_if_current(s, log)]
    if missing:
        raise BootError(
            f"[{scope}] cannot provision (source={source}, R2 creds "
            f"{'present' if r2_creds_present() else 'absent'}, no github_release fallback); "
            f"missing: {', '.join(missing)}. Set the R2_* vars or place the files on the volume.")


def _dry_run(specs_by_scope: dict, log: Log) -> int:
    """Log the boot plan without any network or download: each file's dest, presence, expected
    hash, and where it would come from. Safe to run anywhere (no creds, no fetch)."""
    creds = r2_creds_present()
    log(f"== DRY RUN: boot provisioning plan (R2 creds {'present' if creds else 'absent'}, no network) ==")
    for scope, specs in specs_by_scope.items():
        for s in specs:
            exists = s.dest.exists()
            size = _mb(s.dest.stat().st_size) if exists else "-"
            if s.source == "r2" and creds:
                origin = f"R2 s3://{os.environ.get('R2_BUCKET')}/{s.r2_key}"
            elif s.release_base_url:
                origin = f"github_release {s.release_base_url}/{s.release_asset}"
            elif s.source == "r2":
                origin = f"R2 s3://<bucket>/{s.r2_key} (R2 vars ABSENT, no fallback -> would fail fast)"
            else:
                origin = "github_release (DATA_RELEASE_URL unset)"
            action = "present (would verify + skip if hash matches)" if exists else "MISSING -> would download"
            sha = (s.sha256[:16] + "...") if s.sha256 else "(release-verified)"
            log(f"  [{scope}/{s.kind}] {action}")
            log(f"      dest={s.dest} size={size} sha256={sha} <- {origin}")
    log("== END DRY RUN ==")
    return 0


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()   # match the serve layer: CIVIC_* + R2_* from .env, never overriding real env vars

    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args
    log: Log = lambda m: print(m, flush=True)  # noqa: E731

    try:
        registry = scopes.load_registry()
    except scopes.ScopeError as exc:
        log(f"BOOT FAILED: {exc}")
        return 1

    names = enabled_for_boot(registry, os.environ.get(ENV_ENABLED_SCOPES))
    log(f"boot: provisioning scopes {names} (source per config/scopes.toml)")

    try:
        specs_by_scope = {n: scope_provision_specs(n, registry=registry) for n in names}
    except (scopes.ScopeError, BootError) as exc:
        log(f"BOOT FAILED: {exc}")
        return 1

    if dry_run:
        return _dry_run(specs_by_scope, log)

    client_box: dict = {"c": None}

    def get_client():
        if client_box["c"] is None:
            client_box["c"] = make_r2_client()
        return client_box["c"]

    try:
        for name in names:
            provision_scope(specs_by_scope[name], log, get_client=get_client)
    except BootError as exc:
        log(f"BOOT FAILED: {exc}")
        return 1

    log("boot: all enabled scopes provisioned and verified; serving")
    return 0


if __name__ == "__main__":
    sys.exit(main())
