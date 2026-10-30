"""Upload the derived release files (dense artifacts, corpus facts) to the private R2 bucket. OPERATOR-RUN.

Reaches Cloudflare R2, so the account owner runs it (docs/v2/HOSTING.md, step 2). Each file is
checked against the sha256 recorded in config/scopes.toml before it is uploaded, and its size is
checked on R2 afterwards. An object already on R2 with the right size is skipped. Credentials come
only from the environment (R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY: a token
that can write to the bucket); nothing about them is printed. Needs boto3.

    python scripts/v2/upload_artifacts.py --src C:/civic-measure/src
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, type=Path, help="folder holding the verified artifacts")
    args = parser.parse_args(argv)
    missing = [v for v in ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not os.environ.get(v)]
    if missing:
        print(f"set {', '.join(missing)} in the environment first", file=sys.stderr)
        return 2
    sys.path.insert(0, str(REPO / "src"))
    from archive_debugger import release_files
    from archive_debugger.boot import make_r2_client
    from archive_debugger.retrieve.dense import file_sha256

    client = make_r2_client()
    bucket = os.environ["R2_BUCKET"]
    derived = [f for f in release_files.all_files() if f.kind not in ("db", "index")]
    for f in derived:
        key = f.key
        path = f.path(args.src)
        expected = f.sha256
        actual = file_sha256(path)
        if actual != expected:
            print(f"{path}: sha256 does not match config/scopes.toml; nothing uploaded", file=sys.stderr)
            return 1
        size = path.stat().st_size
        try:
            head = client.head_object(Bucket=bucket, Key=key)
            if int(head["ContentLength"]) == size:
                print(f"skip {key}: already on R2 with the same size")
                continue
        except Exception:  # noqa: BLE001 - not there yet
            pass
        print(f"uploading {key} ({size:,} bytes)", flush=True)
        client.upload_file(str(path), bucket, key)
        head = client.head_object(Bucket=bucket, Key=key)
        if int(head["ContentLength"]) != size:
            print(f"{key}: size on R2 differs after upload", file=sys.stderr)
            return 1
        print(f"uploaded {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
