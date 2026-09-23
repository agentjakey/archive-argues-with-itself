"""Upload both scopes' database + index files to Cloudflare R2 and print their sha256.

OPERATOR-RUN, NETWORK-ON. This reaches Cloudflare R2 (the S3 API), so it is NOT run in
the session (N1): you run it yourself in your terminal. It never modifies a database
(read-only uploads) and it never writes your R2 secret anywhere. The secret is read from
the environment (R2_SECRET_ACCESS_KEY) or, if that is unset, from a no-echo prompt at
runtime; it is never printed, defaulted, or saved to any file.

The four files come from config/scopes.toml, resolved exactly as the app resolves them:

  pilot     civic.db  + index/vectors.db   (inherit scope: config/pilot.toml + CIVIC_* env,
                                            so the deploy's C:\\civic-data store is honored)
  microlog  civic_microlog.db + vectors_microlog.db   (registry paths under
                                            data/exploration/microlog/)

They upload to the keys pilot/<filename> and microlog/<filename> in the bucket. An object
that already exists with a matching size AND sha256 is skipped ("skip, already current"),
so re-running is cheap and idempotent.

Prereq: boto3 (in the dev extra: pip install -e .[dev] --break-system-packages, or
pip install boto3 --break-system-packages).

Export first (all but the secret; the secret is prompted for if unset):

    export R2_ENDPOINT="https://<accountid>.r2.cloudflarestorage.com"
    export R2_BUCKET="<bucket-name>"
    export R2_ACCESS_KEY_ID="<access-key-id>"
    # R2_SECRET_ACCESS_KEY optional; if unset you are prompted with no echo

Then, from the repo root:

    python scripts/upload_scopes_to_r2.py
    # or with this repo's venv:
    .venv/Scripts/python.exe scripts/upload_scopes_to_r2.py

The four sha256 hashes are also written to scopes.r2.sha256 at the repo root (hashes and
file identities only, never a secret) so you can paste them into the wire-up prompt.
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
from getpass import getpass
from pathlib import Path

# Repo root = the parent of this scripts/ directory. Everything below is anchored here so
# the config-relative paths (config/scopes.toml, data/exploration/microlog/...) resolve no
# matter which directory the operator launches from.
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
HASH_OUT = REPO / "scopes.r2.sha256"

HASH_CHUNK = 8 * 1024 * 1024        # 8 MiB streaming read for sha256 (handles multi-GB files)
PART_SIZE = 64 * 1024 * 1024        # 64 MiB multipart part size (S3 minimum is 5 MiB)
MULTIPART_THRESHOLD = 64 * 1024 * 1024

ENV_REQUIRED = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID")
ENV_SECRET = "R2_SECRET_ACCESS_KEY"

# Custom object-metadata key that carries the file's sha256. S3/R2 lowercases metadata keys
# and returns them under head_object()["Metadata"], so skip-if-current and post-upload verify
# both compare against this value rather than the ETag (a multipart ETag is not a plain md5).
META_SHA = "sha256"


def die(message: str) -> "NoReturn":  # type: ignore[valid-type]
    """Fail loudly and clearly, then exit non-zero. Never includes the secret."""
    sys.stderr.write(f"ABORT: {message}\n")
    raise SystemExit(1)


def human(nbytes: int) -> str:
    """A short human-readable size, e.g. '1.72 GB'."""
    value = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{nbytes} B"


def resolve_targets() -> list[dict]:
    """The four files to upload, resolved from config/scopes.toml the same way the serve
    layer does. Returns a list of {scope, kind, path, key}. Aborts if any file is missing."""
    os.chdir(REPO)                                  # config/data paths are repo-relative
    if SRC.is_dir() and str(SRC) not in sys.path:   # importable without an editable install
        sys.path.insert(0, str(SRC))
    try:
        from dotenv import load_dotenv              # match the app: honor .env's CIVIC_* paths
        load_dotenv(".env")                         # never overrides real exported env vars
    except Exception:
        pass

    try:
        from archive_debugger import scopes
    except Exception as exc:
        die(f"could not import archive_debugger from {SRC} ({exc}); run from the repo with its venv")

    targets: list[dict] = []
    for name in ("pilot", "microlog"):
        try:
            scope = scopes.resolve_scope(name)
        except Exception as exc:
            die(f"could not resolve scope {name!r} from config/scopes.toml: {exc}")
        for kind, path in (("db", Path(scope.db_path)), ("index", Path(scope.index_path))):
            targets.append({"scope": name, "kind": kind, "path": path, "key": f"{name}/{path.name}"})

    print("Resolved scope files (from config/scopes.toml):")
    missing: list[dict] = []
    for t in targets:
        exists = t["path"].is_file()
        if exists:
            size = t["path"].stat().st_size
            t["size"] = size
            print(f"  [OK]      {t['scope']:9} {t['kind']:5} {t['path']}  ({human(size)})")
        else:
            missing.append(t)
            print(f"  [MISSING] {t['scope']:9} {t['kind']:5} {t['path']}")
    if missing:
        names = "; ".join(f"{t['scope']}/{t['kind']} -> {t['path']}" for t in missing)
        die(f"missing file(s): {names}")
    return targets


def sha256_of(path: Path) -> str:
    """Streamed sha256 of a possibly multi-GB file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(HASH_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def read_r2_config() -> dict:
    """R2 endpoint/bucket/key from the environment; secret from the environment or a no-echo
    prompt. The secret is never printed, defaulted, or written anywhere."""
    values = {name: os.environ.get(name, "").strip() for name in ENV_REQUIRED}
    missing = [name for name, val in values.items() if not val]
    if missing:
        die(f"missing environment variable(s): {', '.join(missing)}. Export them first "
            f"(see the header of this script).")
    secret = os.environ.get(ENV_SECRET, "").strip()
    if not secret:
        secret = getpass(f"{ENV_SECRET} (input hidden): ").strip()
    if not secret:
        die(f"{ENV_SECRET} was empty; set it in the environment or enter it at the prompt.")
    values[ENV_SECRET] = secret
    return values


def make_client(cfg: dict):
    """An S3 client pointed at the R2 endpoint. boto3 is imported here so the path and hash
    steps still run (and still write scopes.r2.sha256) even if boto3 is not installed yet."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        die("boto3 is required for the upload. Install it: pip install -e .[dev] "
            "--break-system-packages  (or: pip install boto3 --break-system-packages)")
    return boto3.client(
        "s3",
        endpoint_url=cfg["R2_ENDPOINT"],
        aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg[ENV_SECRET],
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )


def head(client, bucket: str, key: str):
    """head_object result, or None if the object does not exist."""
    from botocore.exceptions import ClientError
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        die(f"could not query {key} on R2: {exc}")
    except Exception as exc:
        die(f"could not query {key} on R2: {exc}")


def upload_one(client, bucket: str, target: dict, sha: str) -> str:
    """Multipart upload with a per-file progress line. Skips if the object already exists with
    a matching size AND sha256. Returns 'uploaded' or 'skip'. Fails loudly, naming file + key."""
    from boto3.s3.transfer import TransferConfig
    path, key, size = target["path"], target["key"], target["size"]

    existing = head(client, bucket, key)
    if existing is not None:
        remote_size = existing.get("ContentLength")
        remote_sha = (existing.get("Metadata") or {}).get(META_SHA)
        if remote_size == size and remote_sha == sha:
            print(f"  skip, already current: {key} ({human(size)})")
            return "skip"

    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=PART_SIZE,
        max_concurrency=4,
        use_threads=True,
    )
    sent = {"n": 0}
    lock = threading.Lock()

    def progress(chunk: int) -> None:
        with lock:
            sent["n"] += chunk
            pct = (100.0 * sent["n"] / size) if size else 100.0
            sys.stdout.write(f"\r  uploading {key}: {human(sent['n'])}/{human(size)} ({pct:5.1f}%)")
            sys.stdout.flush()

    try:
        client.upload_file(
            str(path), bucket, key,
            ExtraArgs={"Metadata": {META_SHA: sha}},
            Config=config,
            Callback=progress,
        )
    except Exception as exc:
        sys.stdout.write("\n")
        die(f"upload failed for {path} -> s3://{bucket}/{key}: {exc}")
    sys.stdout.write("\n")
    return "uploaded"


def verify_one(client, bucket: str, target: dict, sha: str) -> str:
    """Read the object back and confirm size (and sha256 metadata when returned). Returns 'ok',
    a size-only note if R2 does not echo the metadata, or a 'FAILED: ...' reason."""
    result = head(client, bucket, target["key"])
    if result is None:
        return "FAILED: object not found after upload"
    remote_size = result.get("ContentLength")
    remote_sha = (result.get("Metadata") or {}).get(META_SHA)
    if remote_size != target["size"]:
        return f"FAILED: size {remote_size} != {target['size']}"
    if remote_sha is None:
        return "ok (size only; sha256 metadata not returned)"
    if remote_sha != sha:
        return f"FAILED: sha256 metadata {remote_sha[:16]}... != local"
    return "ok"


def write_hash_file(targets: list[dict]) -> None:
    """Write scopes.r2.sha256 at the repo root: sha256, key, and size only. No secrets."""
    lines = ["# sha256 of the scope database + index files uploaded to Cloudflare R2.",
             "# Format: <sha256>  <key>  (<bytes> bytes). No secrets are stored here.",
             ""]
    lines += [f"{t['sha']}  {t['key']}  ({t['size']} bytes)" for t in targets]
    HASH_OUT.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> int:
    targets = resolve_targets()

    print("\nComputing sha256:")
    for t in targets:
        t["sha"] = sha256_of(t["path"])
        print(f"  {t['sha']}  {t['key']}")
    write_hash_file(targets)
    print(f"\nWrote hashes to {HASH_OUT}")

    cfg = read_r2_config()
    client = make_client(cfg)
    print(f"\nUploading to bucket {cfg['R2_BUCKET']} at {cfg['R2_ENDPOINT']}:")
    for t in targets:
        t["action"] = upload_one(client, cfg["R2_BUCKET"], t, t["sha"])

    print("\nVerifying:")
    for t in targets:
        if t["action"] == "skip":
            t["verify"] = "ok (skip: size + sha256 already matched)"
        else:
            t["verify"] = verify_one(client, cfg["R2_BUCKET"], t, t["sha"])
        print(f"  {t['key']}: {t['verify']}")

    print("\n" + "=" * 100)
    print(f"{'key':30} {'size (bytes)':>16}  {'sha256 (first 16)':19}  status")
    print("-" * 100)
    all_ok = True
    for t in targets:
        status = f"{t['action']}, {t['verify']}"
        if t["verify"].startswith("FAILED"):
            all_ok = False
        print(f"{t['key']:30} {t['size']:>16}  {t['sha'][:16] + '...':19}  {status}")
    print("=" * 100)

    if not all_ok:
        die("one or more files failed verification; see the table above.")
    print("\nDone. All four files are current in R2 and verified. "
          "Paste scopes.r2.sha256 into the wire-up prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
