"""Time the R2 part of a cold boot: download each scope's two objects, then verify their sha256.

The same client (archive_debugger.boot.make_r2_client, from the R2_* environment variables) and
the same expected hashes (config/scopes.toml) as the boot, but into a scratch directory you name,
so nothing serving is touched. Download and hash verification are timed separately. The scratch
directory must be empty; the downloaded files are deleted at the end unless --keep is passed.

Credentials come only from the environment (R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY); a read-only token is enough. Nothing is printed about them.

    python scripts/v2/time_r2_fetch.py --dest D:/r2-timing --scopes pilot,microlog \
        --out reports/v2/raw/r2_fetch.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

from archive_debugger import boot, scopes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", required=True, help="an EMPTY scratch directory on the disk being measured")
    parser.add_argument("--scopes", default="", help="comma-separated scopes; default: every scope in config/scopes.toml")
    parser.add_argument("--out", required=True)
    parser.add_argument("--where", default="", help="free text: where this ran (e.g. home network, a Cloudflare container)")
    parser.add_argument("--keep", action="store_true", help="keep the downloaded files")
    args = parser.parse_args(argv)

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        print(f"refusing to run: {dest} is not empty", file=sys.stderr)
        return 2
    registry = scopes.load_registry()
    client = boot.make_r2_client()
    bucket = os.environ["R2_BUCKET"]
    rows = []
    t_all = time.monotonic()
    try:
        from archive_debugger import release_files
        for scope in [s.strip() for s in args.scopes.split(",") if s.strip()] or release_files.scope_names():
            for spec in boot.scope_provision_specs(scope, registry=registry):
                target = dest / spec.r2_key.replace("/", "__")
                t0 = time.monotonic()
                client.download_file(bucket, spec.r2_key, str(target))
                t1 = time.monotonic()
                got = boot.sha256_file(target, lambda m: None)
                t2 = time.monotonic()
                size = target.stat().st_size
                row = {"scope": scope, "kind": spec.kind, "key": spec.r2_key, "bytes": size,
                       "download_seconds": round(t1 - t0, 2), "verify_seconds": round(t2 - t1, 2),
                       "download_mb_per_s": round(size / 2**20 / max(t1 - t0, 1e-9), 1),
                       "sha256_ok": got == spec.sha256}
                rows.append(row)
                print(json.dumps(row), flush=True)
                if not args.keep:
                    target.unlink()
    finally:
        if not args.keep:
            shutil.rmtree(dest, ignore_errors=True)
    record = {"where": args.where, "host": platform.node(), "python": platform.python_version(),
              "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "total_seconds": round(time.monotonic() - t_all, 2), "files": rows,
              "all_sha256_ok": all(r["sha256_ok"] for r in rows)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "files"}))
    return 0 if record["all_sha256_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
