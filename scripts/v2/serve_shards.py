"""Register built shards as served engine scopes: config/shards/served.toml.

    python scripts/v2/serve_shards.py register --shard federal-1899-1911
    python scripts/v2/serve_shards.py register --shard british_columbia-1968-2001 \
        --local data/bounded/bc_govpubs/shards/british_columbia-1968-2001 --describe data/bounded/bc_govpubs/shards.json \
        --prefix shards/bounded
    python scripts/v2/serve_shards.py remove --shard federal-1899-1911
    python scripts/v2/serve_shards.py list

Each served shard is one scope, and so one engine container in the engine Worker's split layout: no
shard is named in code. A shard's registry entry names its corpus database on R2 (from the shard
builder's manifest, <prefix>/<shard>/manifest.json, with its sha256) and an empty vectors database
written here, because the whole collection is served with BM25 alone (config/shards/engine.toml).
With --local, a shard built elsewhere (the bounded run) is uploaded first, under --prefix.

The tier starts at INDEXED. It changes only through `tier`, after the shard's audit
(docs/v2/AUDIT_PIPELINE.md): AI-AUDITED needs the audit's published error rate. After any change,
run scripts/v2/export_worker_config.py so the engine Worker's generated config matches.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.jobs.store import R2Store, sha256_file  # noqa: E402
from archive_debugger.retrieve.index import VEC_SCHEMA  # noqa: E402

SERVED = REPO / "config" / "shards" / "served.toml"
PLAN = REPO / "config" / "shards" / "plan.json"
ENGINE_CONFIG = "config/shards/engine.toml"
TIERS = ("INDEXED", "AI-AUDITED", "HUMAN-AUDITED")
PLACE_NAMES = {
    "federal": "Government of Canada", "alberta": "Alberta", "british_columbia": "British Columbia",
    "manitoba": "Manitoba", "new_brunswick": "New Brunswick", "newfoundland_and_labrador": "Newfoundland and Labrador",
    "nova_scotia": "Nova Scotia", "ontario": "Ontario", "prince_edward_island": "Prince Edward Island",
    "quebec": "Quebec", "saskatchewan": "Saskatchewan", "northwest_territories": "Northwest Territories",
    "nunavut": "Nunavut", "yukon": "Yukon", "other": "Other jurisdictions",
}


def read_served() -> dict:
    if not SERVED.exists():
        return {}
    with SERVED.open("rb") as fh:
        return tomllib.load(fh).get("scopes") or {}


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=True)


def write_served(scopes: dict) -> None:
    """TOML by hand (the standard library reads TOML but does not write it): flat keys, then each
    nested table, in a fixed order so the file only changes when a shard does."""
    lines = ["# Served shards of the whole collection, one engine scope each. Written by",
             "# scripts/v2/serve_shards.py; do not edit by hand. Read with config/scopes.toml by",
             "# archive_debugger.scopes.load_registry.", ""]
    for name in sorted(scopes):
        entry = scopes[name]
        lines.append(f"[scopes.{json.dumps(name)}]")
        for key in sorted(k for k, v in entry.items() if not isinstance(v, dict)):
            lines.append(f"{key} = {_value(entry[key])}")
        for table in sorted(k for k, v in entry.items() if isinstance(v, dict)):
            lines.append("")
            lines.append(f"[scopes.{json.dumps(name)}.{table}]")
            for key in sorted(entry[table]):
                lines.append(f"{key} = {_value(entry[table][key])}")
        lines.append("")
    SERVED.parent.mkdir(parents=True, exist_ok=True)
    SERVED.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def describe(shard_id: str, describe_path: Path = None) -> dict:
    rows = json.loads((describe_path or PLAN).read_text(encoding="utf-8"))
    shards = rows["shards"] if isinstance(rows, dict) else rows
    for s in shards:
        if s["shard_id"] == shard_id:
            return s
    raise SystemExit(f"{shard_id} is not in {describe_path or PLAN}")


def label(shard: dict) -> str:
    places = [PLACE_NAMES.get(j, j.replace("_", " ").title()) for j in shard.get("jurisdictions") or [shard["jurisdiction"]]]
    where = ", ".join(places[:3]) + (f" and {len(places) - 3} more" if len(places) > 3 else "")
    when = "undated" if shard.get("undated") else f"{shard['first_year']} to {shard['last_year']}"
    return f"{where}, {when}"


def empty_vectors(folder: Path) -> Path:
    path = folder / "vectors.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(VEC_SCHEMA)
    conn.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES ('count', '0')")
    conn.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES ('note', 'BM25 alone: no dense vectors')")
    conn.commit()
    conn.close()
    return path


def entry_for(shard: dict, prefix: str, db_sha: str, index_sha: str, tier: str = "INDEXED") -> dict:
    sid = shard["shard_id"]
    return {
        "config": ENGINE_CONFIG,
        "db_path": f"data/shards/{sid}/civic.db",
        "index_path": f"data/shards/{sid}/index/vectors.db",
        "source": "r2",
        "release_dir": f"shards/{sid}",
        "label": label(shard),
        "blurb": f"{shard.get('documents', 0):,} publications from Internet Archive Canada's government collection",
        "jurisdiction_phrase": label(shard).rsplit(", ", 1)[0],
        "national": False,
        "collection": "governmentpublications",
        "tier": tier,
        "shard": {"jurisdictions": shard.get("jurisdictions") or [shard["jurisdiction"]],
                  "first_year": shard.get("first_year") or 0, "last_year": shard.get("last_year") or 0,
                  "undated": bool(shard.get("undated")), "documents": int(shard.get("documents") or 0)},
        "r2": {"db_key": f"{prefix}/{sid}/civic.db", "db_sha256": db_sha,
               "index_key": f"{prefix}/{sid}/vectors.db", "index_sha256": index_sha},
    }


def cmd_register(args) -> int:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)          # the R2 credentials, from the environment or .env
    r2 = R2Store()
    sid = args.shard
    shard = describe(sid, Path(args.describe) if args.describe else None)
    if args.local:
        db = Path(args.local) / "civic.db"
        db_sha = r2.put_file(f"{args.prefix}/{sid}/civic.db", db)["sha256"]
    else:
        raw = r2.get(f"{args.prefix}/{sid}/manifest.json")
        if raw is None:
            raise SystemExit(f"{args.prefix}/{sid}/manifest.json is not on R2: build the shard first")
        manifest = json.loads(raw)
        if manifest.get("partial"):
            raise SystemExit(f"{sid} is a partial (trial) build and is never served")
        db_sha = manifest["files"]["civic.db"]["sha256"]
    with tempfile.TemporaryDirectory() as tmp:
        vec = empty_vectors(Path(tmp))
        index_sha = r2.put_file(f"{args.prefix}/{sid}/vectors.db", vec)["sha256"]
        if index_sha != sha256_file(vec):
            raise SystemExit("the vectors database on R2 does not match the one written")
    served = read_served()
    tier = (served.get(sid) or {}).get("tier", "INDEXED")
    served[sid] = entry_for(shard, args.prefix, db_sha, index_sha, tier)
    write_served(served)
    print(json.dumps({"registered": sid, "label": served[sid]["label"], "tier": tier, "db_sha256": db_sha}))
    return 0


def cmd_remove(args) -> int:
    served = read_served()
    if served.pop(args.shard, None) is None:
        print(f"{args.shard} is not served")
        return 1
    write_served(served)
    print(json.dumps({"removed": args.shard}))
    return 0


def cmd_tier(args) -> int:
    served = read_served()
    if args.shard not in served:
        raise SystemExit(f"{args.shard} is not served")
    if args.tier == "AI-AUDITED" and not args.audit:
        raise SystemExit("AI-AUDITED needs --audit naming the audit whose error rate is published")
    served[args.shard]["tier"] = args.tier
    if args.audit:
        served[args.shard]["audit"] = args.audit
    write_served(served)
    print(json.dumps({"shard": args.shard, "tier": args.tier}))
    return 0


def cmd_list(args) -> int:
    for sid, e in sorted(read_served().items()):
        print(f"{sid:32} {e.get('tier', 'INDEXED'):14} {e['label']}  ({e['r2']['db_key']})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("register")
    p.add_argument("--shard", required=True)
    p.add_argument("--prefix", default="shards/v1")
    p.add_argument("--local", default=None, help="a folder with civic.db to upload (a shard built elsewhere)")
    p.add_argument("--describe", default=None, help="a JSON list of shard descriptions (default: the plan)")
    p.set_defaults(fn=cmd_register)
    p = sub.add_parser("remove")
    p.add_argument("--shard", required=True)
    p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("tier")
    p.add_argument("--shard", required=True)
    p.add_argument("--tier", choices=TIERS, required=True)
    p.add_argument("--audit", default=None)
    p.set_defaults(fn=cmd_tier)
    p = sub.add_parser("list")
    p.set_defaults(fn=cmd_list)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
