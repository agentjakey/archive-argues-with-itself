"""The router index on R2: what the engine Worker reads to choose which shard engines to wake for a
whole-collection question, without waking any (docs/formats/shards.md, "Router index").

    python scripts/v2/router_index.py build [--compute-missing] [--dry-run]

For every shard in config/shards/served.toml, and every part config/shards/router.toml names (the
collections served before the shards, keyed in config/scopes.toml), it reads the coverage file (coverage.json beside
the shard's corpus database on R2, written by shard_builder.py). With --compute-missing, a shard
without one (the bounded run's shards) has its database downloaded, its coverage computed with the
same code and uploaded beside it. Then it writes, under a new content-addressed folder:

  router/v1/<digest>/df/<bucket>.tsv   one line per term: term TAB shard:df,shard:df,...
                                       (bucket = FNV-1a 32-bit of the term's UTF-8 bytes mod BUCKETS)
and last the pointer the Worker reads:
  router/v1/shards.json                {format, digest, prefix, buckets, built_at, N, tokens, avgdl,
                                        shards: {id: {jurisdictions, years, passages, tokens, tier}}}

Writing the pointer last means the Worker never reads a half-written index; earlier folders stay.
Which shards a deployment may wake is still decided by its SHARDS variable."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.shards import coverage as coverage_mod  # noqa: E402

SERVED = REPO / "config" / "shards" / "served.toml"
ROUTER = REPO / "config" / "shards" / "router.toml"
SCOPES = REPO / "config" / "scopes.toml"
PREFIX = "router/v1"
BUCKETS = 4096
FORMAT = 1


def fnv1a(term: str) -> int:
    h = 0x811C9DC5
    for byte in term.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def bucket_of(term: str, buckets: int = BUCKETS) -> int:
    return fnv1a(term) % buckets


def bucket_name(n: int) -> str:
    return f"{n:04d}"


def served() -> dict:
    if not SERVED.exists():
        return {}
    with SERVED.open("rb") as fh:
        return tomllib.load(fh).get("scopes") or {}


def parts() -> dict:
    """The always-served parts (router.toml parts) as served-style entries: their R2 keys from
    config/scopes.toml, tier from the same file when it names one."""
    with ROUTER.open("rb") as fh:
        names = tomllib.load(fh).get("parts") or []
    with SCOPES.open("rb") as fh:
        scopes = tomllib.load(fh).get("scopes") or {}
    return {n: {"r2": scopes[n]["r2"], "tier": scopes[n].get("tier"), "local": local_db(n, scopes[n])}
            for n in names if n in scopes and "r2" in scopes[n]}


def local_db(name: str, entry: dict) -> str | None:
    """A local copy of the part's database, used instead of a download when its hash is the one R2
    serves; None when there is none."""
    path = REPO / entry["db_path"] if entry.get("db_path") else None
    if path is None or not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            h.update(block)
    return str(path) if h.hexdigest() == entry["r2"].get("db_sha256") else None


def coverage_key(entry: dict) -> str:
    return entry["r2"]["db_key"].rsplit("/", 1)[0] + "/coverage.json"


def load_coverage(r2, sid: str, entry: dict, compute_missing: bool) -> dict:
    key = coverage_key(entry)
    if r2.head(key) is not None:
        return json.loads(r2.get(key))
    if not compute_missing:
        raise SystemExit(f"{key} is not on R2 (run with --compute-missing to compute it from the shard's database)")
    with tempfile.TemporaryDirectory() as tmp:
        if entry.get("local"):
            db = Path(entry["local"])
        else:
            db = Path(tmp) / "civic.db"
            db.write_bytes(r2.get(entry["r2"]["db_key"]))
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cov = coverage_mod.compute(conn, sid)
        conn.close()
    r2.put(key, json.dumps(cov).encode("utf-8"))
    return cov


def build(coverages: dict, tiers: dict, buckets: int = BUCKETS) -> tuple:
    """(files, pointer): {bucket name: tsv bytes} and the shards.json document (without prefix)."""
    rows: dict = {}
    for sid in sorted(coverages):
        for term, df in coverages[sid]["df"].items():
            rows.setdefault(term, []).append(f"{sid}:{int(df)}")
    by_bucket: dict = {}
    for term in sorted(rows):
        if "\t" in term or "\n" in term:
            continue
        by_bucket.setdefault(bucket_of(term, buckets), []).append(f"{term}\t{','.join(rows[term])}\n")
    files = {bucket_name(n): "".join(by_bucket.get(n, [])).encode("utf-8") for n in range(buckets)}
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode() + b"\0" + files[name])
    n = sum(c["passages"] for c in coverages.values())
    tokens = sum(c["tokens"] for c in coverages.values())
    pointer = {"format": FORMAT, "digest": digest.hexdigest()[:16], "buckets": buckets, "N": n, "tokens": tokens,
               "avgdl": tokens / n if n else 0.0,
               "shards": {sid: {"jurisdictions": c["jurisdictions"], "years": c["years"], "passages": c["passages"],
                                "tokens": c["tokens"], "tier": tiers.get(sid)} for sid, c in sorted(coverages.items())}}
    return files, pointer


def cmd_build(args) -> int:
    from archive_debugger.jobs.store import R2Store
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)
    r2 = R2Store()
    entries = {**served(), **parts()}
    if not entries:
        raise SystemExit("no served shards in config/shards/served.toml")
    coverages = {sid: load_coverage(r2, sid, e, args.compute_missing) for sid, e in sorted(entries.items())}
    files, pointer = build(coverages, {sid: e.get("tier") for sid, e in entries.items()})
    prefix = f"{PREFIX}/{pointer['digest']}"
    pointer.update(prefix=prefix, built_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    summary = {"shards": len(coverages), "terms_bytes": sum(len(b) for b in files.values()), "prefix": prefix,
               "N": pointer["N"]}
    if args.dry_run:
        print(json.dumps(summary))
        return 0
    if r2.head(f"{prefix}/complete") is None:
        for name, body in files.items():
            r2.put(f"{prefix}/df/{name}.tsv", body)
        r2.put(f"{prefix}/complete", b"ok")
    r2.put(f"{PREFIX}/shards.json", json.dumps(pointer, sort_keys=True).encode("utf-8"))
    print(json.dumps(summary))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--compute-missing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_build)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
