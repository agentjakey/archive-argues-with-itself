"""Build the whole collection's engine shards on this laptop as the full text arrives.

    python scripts/v2/shard_builder.py order            # write the fetch order: shard by shard
    python scripts/v2/shard_builder.py status           # one line per shard: fetched, built, uploaded
    python scripts/v2/shard_builder.py run [--once]     # build every shard whose text is all fetched
    python scripts/v2/shard_builder.py build --shard <id> [--allow-partial]   # one shard now

`order` writes data/fulltext/order.txt, which the full-text fetch follows: the shards with the most
text already fetched come first, then the smaller ones, so shards complete one at a time instead of
all at the end.

`run` loops (a detached background job; it resumes from its own state after any stop): for each shard
of config/shards/plan.json whose documents all have a fetch record, it builds the shard:

  1. waits for the heavy lock (.cc-heavy.lock in the main checkout), at least MIN_FREE_MEMORY_GB of
     free memory, and the shard's estimated size plus KEEP_FREE_DISK_GB of free disk;
  2. compiles the fetched text into units of UNIT_ITEMS documents (data/build/<shard>/units/,
     resumable: a unit already written is not compiled again);
  3. packs the units into the shard's corpus database with the corpus builder's schema, places from
     the registry (the bounded run's packing, unchanged);
  4. computes its static coverage file and the embedding input (the passages, in files of
     EMBED_UNIT passages, the embed job's input format);
  5. uploads everything to R2 under shards/v1/<shard>/ with a manifest of sha256 checksums, reads
     the manifest back, and only then deletes the local units and database.

The fetched text itself stays (it is the fetch's own record). State: data/build/state.json and
shards/v1/<shard>/manifest.json on R2 (a shard whose manifest is on R2 is never built again).
Nothing here calls a paid API."""
from __future__ import annotations

import argparse
import ctypes
import gzip
import json
import os
import shutil
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.jobs import compile as compile_job, embed as embed_job  # noqa: E402
from archive_debugger.shards import coverage as coverage_mod  # noqa: E402

PLAN = REPO / "config" / "shards" / "plan.json"
MEMBERS = REPO / "data" / "shards" / "members.tsv"
FULLTEXT = REPO / "data" / "fulltext"
BUILD = REPO / "data" / "build"
CATALOGUE = REPO / "data" / "catalogue" / "catalogue.jsonl.gz"
REGISTRY = REPO / "data" / "registry" / "registry.db"
MAIN_CHECKOUT = Path(os.environ.get("ARCHIVE_ARGUES_MAIN", r"C:\Users\profe\OneDrive\Desktop\python\archive-argues-with-itself"))
LOCK = MAIN_CHECKOUT / ".cc-heavy.lock"
R2_PREFIX = "shards/v1"
TRIAL_PREFIX = "shards/trial"
UNIT_ITEMS = 200
EMBED_UNIT = 10_000
MIN_FREE_MEMORY_GB = 4.0
KEEP_FREE_DISK_GB = 50.0
POLL_S = 600
OWNER = f"runB shard_builder pid {os.getpid()} on {socket.gethostname()}"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{now()} {msg}"
    print(line, flush=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    with (BUILD / "builder.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# --- resources -------------------------------------------------------------------------------------

class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_memory_gb() -> float:
    if sys.platform == "win32":
        status = _MemStatus()
        status.dwLength = ctypes.sizeof(_MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullAvailPhys / 2 ** 30
    with open("/proc/meminfo", encoding="ascii") as fh:
        info = {l.split(":")[0]: int(l.split()[1]) for l in fh}
    return info["MemAvailable"] / 2 ** 20


def free_disk_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 2 ** 30


def take_lock() -> bool:
    """True when this process holds the heavy lock. A lock held by anyone else is waited for."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            return LOCK.read_text(encoding="ascii").strip() == OWNER
        except OSError:
            return False
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(OWNER)
    return True


def release_lock() -> None:
    try:
        if LOCK.read_text(encoding="ascii").strip() == OWNER:
            LOCK.unlink()
    except OSError:
        pass


def wait_for_resources(need_disk_gb: float) -> None:
    """Block until the lock, memory and disk allow a build; say what is being waited for."""
    said = None
    while True:
        reasons = []
        if free_memory_gb() < MIN_FREE_MEMORY_GB:
            reasons.append(f"free memory {free_memory_gb():.1f} GB < {MIN_FREE_MEMORY_GB} GB")
        if free_disk_gb(BUILD) < need_disk_gb + KEEP_FREE_DISK_GB:
            reasons.append(f"free disk {free_disk_gb(BUILD):.0f} GB < {need_disk_gb:.0f} + {KEEP_FREE_DISK_GB:.0f} GB")
        if not reasons and not take_lock():
            reasons.append("the heavy lock is held: " + (LOCK.read_text(encoding="ascii", errors="replace").strip()[:120]
                                                         if LOCK.exists() else "?"))
        if not reasons:
            return
        if reasons != said:
            log("waiting: " + "; ".join(reasons))
            said = reasons
        time.sleep(60)


# --- plan, fetch state ----------------------------------------------------------------------------

def load_plan() -> list:
    return json.loads(PLAN.read_text(encoding="utf-8"))["shards"]


def members() -> dict:
    out: dict = {}
    for line in MEMBERS.read_text(encoding="utf-8").splitlines():
        doc, shard = line.split("\t")
        if doc.startswith("ia:"):
            out.setdefault(shard, []).append(doc[3:])
    return out


def fetched() -> dict:
    """{identifier: manifest record} for every item the fetch recorded (errors excluded)."""
    out = {}
    path = FULLTEXT / "manifest.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") != "error":
            out[row["identifier"]] = row
    return out


def cmd_order(args) -> int:
    got = set(fetched())
    by_shard = members()
    shards = load_plan()

    def key(s):
        ids = by_shard.get(s["shard_id"], [])
        done = sum(1 for i in ids if i in got)
        return (-(done / max(1, len(ids))), len(ids), s["shard_id"])
    ordered = sorted(shards, key=key)
    lines = []
    for s in ordered:
        lines += sorted(by_shard.get(s["shard_id"], []))
    (FULLTEXT / "order.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} identifiers in {len(ordered)} shards; first: " +
          ", ".join(f"{s['shard_id']} ({len(by_shard.get(s['shard_id'], []))})" for s in ordered[:5]))
    return 0


# --- build ----------------------------------------------------------------------------------------

def store():
    from archive_debugger.jobs.store import R2Store
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)
    return R2Store()


def built_on_r2(r2, shard_id: str) -> bool:
    return r2.head(f"{R2_PREFIX}/{shard_id}/manifest.json") is not None


def item_files(record: dict) -> dict:
    folder = FULLTEXT / record["identifier"][:2] / record["identifier"]
    return {role: (folder / f["name"]).read_bytes() for role, f in (record.get("files") or {}).items()
            if role in ("searchtext", "pageindex", "page_numbers") and (folder / f["name"]).exists()}


def catalogue_records() -> dict:
    raw = gzip.decompress(CATALOGUE.read_bytes()).decode("utf-8")
    return {json.loads(l)["identifier"]: json.loads(l) for l in raw.splitlines() if l.strip()}


def compile_units(shard_id: str, idents: list, have: dict, records: dict, folder: Path) -> list:
    units = folder / "units"
    units.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in range(0, len(idents), UNIT_ITEMS):
        path = units / f"items-{n // UNIT_ITEMS:05d}.jsonl.gz"
        paths.append(path)
        if path.exists():
            continue
        lines = []
        for ident in idents[n:n + UNIT_ITEMS]:
            rec = have.get(ident)
            files = item_files(rec) if rec else {}
            if "searchtext" not in files or "pageindex" not in files:
                lines.append({"kind": "skipped", "identifier": ident,
                              "reason": f"no page-indexed text ({(rec or {}).get('kind', 'not fetched')})"})
                continue
            lines += compile_job.compile_item(ident, files, records.get(ident, {}), target_tokens=300, overlap_tokens=40)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress("".join(json.dumps(l, ensure_ascii=True) + "\n" for l in lines).encode("utf-8"), mtime=0))
        tmp.replace(path)
    return paths


def pack(shard_id: str, unit_paths: list, folder: Path) -> dict:
    from archive_debugger.ingest import db as ingest_db, normalize
    registry = sqlite3.connect(REGISTRY)

    def normalize_from_registry(conn):
        normalize.normalize_items(conn, REPO / "config")
        for ident, in conn.execute("SELECT item_id FROM items").fetchall():
            place, method = registry.execute("SELECT jurisdiction, jurisdiction_method FROM documents WHERE doc_id = ?",
                                             (f"ia:{ident}",)).fetchone() or ("unknown", "unknown")
            conn.execute("UPDATE items SET jurisdiction_norm = ?, jurisdiction_method = ? WHERE item_id = ?",
                         (place or "unknown", f"registry:{method}", ident))
        conn.commit()
    db_path = folder / "civic.db"
    if db_path.exists():
        db_path.unlink()
    return compile_job.pack_shard([p.read_bytes() for p in unit_paths], db_path, init_db=ingest_db.init_db,
                                  normalize=normalize_from_registry)


def embed_inputs(conn: sqlite3.Connection, folder: Path) -> list:
    out = folder / "embed-input"
    out.mkdir(parents=True, exist_ok=True)
    paths, batch, n = [], [], 0
    for pid, text in conn.execute("SELECT passage_id, text FROM passages ORDER BY passage_id"):
        batch.append({"passage_id": pid, "text": text})
        if len(batch) == EMBED_UNIT:
            paths.append(out / f"{n:05d}.jsonl.gz")
            paths[-1].write_bytes(embed_job.write_shard(batch))
            batch, n = [], n + 1
    if batch:
        paths.append(out / f"{n:05d}.jsonl.gz")
        paths[-1].write_bytes(embed_job.write_shard(batch))
    return paths


def build_shard(shard: dict, idents: list, have: dict, records: dict, r2, *, allow_partial: bool = False) -> dict:
    sid = shard["shard_id"]
    missing = [i for i in idents if i not in have]
    if missing and not allow_partial:
        raise RuntimeError(f"{sid}: {len(missing)} documents not fetched yet")
    # A trial build (documents still missing) has its own folder and R2 prefix and is never recorded
    # as built, so the real build later starts clean.
    trial = bool(missing)
    folder = BUILD / (f"trial-{sid}" if trial else sid)
    prefix = TRIAL_PREFIX if trial else R2_PREFIX
    wait_for_resources(need_disk_gb=2 * float(shard.get("est_wake_gb") or 4))
    try:
        started = time.time()
        log(f"{sid}: compiling {len(idents)} documents ({len(missing)} not fetched)")
        unit_paths = compile_units(sid, sorted(idents), have, records, folder)
        counts = pack(sid, unit_paths, folder)
        conn = sqlite3.connect(folder / "civic.db")
        cov = coverage_mod.compute(conn, sid)
        (folder / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
        inputs = embed_inputs(conn, folder)
        conn.close()
        # The embed job's input layout: <input_prefix>/shards/<unit>.jsonl.gz and units.jsonl.
        units_file = folder / "units.jsonl"
        units_file.write_text("".join(json.dumps({"id": p.name.split(".")[0]}) + "\n" for p in inputs), encoding="utf-8")
        files = {"civic.db": folder / "civic.db", "coverage.json": folder / "coverage.json",
                 "embed-job/units.jsonl": units_file, **{f"embed-job/shards/{p.name}": p for p in inputs}}
        manifest = {"shard_id": sid, "built_at": now(), "builder": OWNER, "documents": len(idents),
                    "not_fetched": len(missing), "partial": bool(missing), **{f"built_{k}": v for k, v in counts.items()},
                    "plan": {k: shard.get(k) for k in ("jurisdiction", "first_year", "last_year", "undated", "documents",
                                                       "est_passages", "documents_sha256")},
                    "files": {}, "seconds": None}
        for name, path in files.items():
            meta = r2.put_file(f"{prefix}/{sid}/{name}", path)
            manifest["files"][name] = {"bytes": path.stat().st_size, "sha256": meta["sha256"]}
        manifest["seconds"] = round(time.time() - started, 1)
        r2.put(f"{prefix}/{sid}/manifest.json", json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
        back = json.loads(r2.get(f"{prefix}/{sid}/manifest.json"))
        for name, entry in back["files"].items():
            head = r2.head(f"{prefix}/{sid}/{name}")
            if head is None or int(head.get("bytes", -1)) != entry["bytes"]:
                raise RuntimeError(f"{sid}: {name} on R2 does not match what was uploaded")
        if not trial:
            state = read_state()
            state[sid] = {k: manifest[k] for k in ("built_at", "documents", "not_fetched", "built_items", "built_passages", "seconds")}
            write_state(state)
        shutil.rmtree(folder)                      # units, database and inputs: R2 holds them now
        log(f"{prefix}/{sid}: built {counts['items']} items, {counts['passages']} passages in {manifest['seconds']} s; on R2; local files removed")
        return manifest
    finally:
        release_lock()


def read_state() -> dict:
    path = BUILD / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_state(state: dict) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    tmp = BUILD / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(BUILD / "state.json")


# --- embed ----------------------------------------------------------------------------------------

EMBED_SPEC = "embed-shard"
WORKERS_AI_USD_PER_M_TOKENS = 0.0118      # bge-m3 on Workers AI, developers.cloudflare.com 2026-10-31
CHARS_PER_TOKEN = 3.5                     # OCR text, multilingual tokenizer: a cautious ratio (chars / 4 measured 294 tokens a passage)
EMBED_CEILING_USD = 150.0                 # Jake's ceiling for the whole collection's embedding


def cmd_estimate(args) -> int:
    """The full embedding cost, before any is spent: the plan's passages times measured characters
    per passage (the bounded run's shards, or the built shards when there are any)."""
    import glob
    chars = n = 0
    for path in glob.glob(str(REPO / "data" / "bounded" / "*" / "shards" / "*" / "civic.db")):
        for (text,) in sqlite3.connect(path).execute("SELECT text FROM passages"):
            chars, n = chars + len(text or ""), n + 1
    per_passage = chars / max(1, n) / CHARS_PER_TOKEN
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    passages = plan["totals"]["est_passages"] if "est_passages" in plan.get("totals", {}) else \
        sum(s["est_passages"] for s in plan["shards"])
    built = sum(v.get("built_passages", 0) for v in read_state().values())
    usd = passages * per_passage / 1e6 * WORKERS_AI_USD_PER_M_TOKENS
    out = {"plan_passages": passages, "built_passages": built, "tokens_per_passage": round(per_passage, 1),
           "basis": f"{n:,} measured passages, characters / {CHARS_PER_TOKEN}", "usd_per_m_tokens": WORKERS_AI_USD_PER_M_TOKENS,
           "estimate_usd": round(usd, 2), "ceiling_usd": EMBED_CEILING_USD, "over_ceiling": usd > EMBED_CEILING_USD,
           "cheapest_alternative": "the laptop's CPU (fastembed, free): measured 29-33 passages a second, about "
                                   f"{passages / 31 / 3600:,.0f} hours for the whole plan"}
    print(json.dumps(out, indent=1))
    return 1 if out["over_ceiling"] else 0


def cmd_embed(args) -> int:
    """Embed built shards with the index spec's model: resumable units (a unit already embedded is not
    embedded again), cost per shard in the embedding ledger, vectors assembled to R2."""
    import dataclasses
    import io
    import numpy as np
    from archive_debugger.jobs import runner, spec as spec_mod
    r2 = store()
    base = spec_mod.load(EMBED_SPEC)
    index = embed_job.load_index_spec(base)["index"]
    targets = [args.shard] if args.shard else sorted(read_state())
    for sid in targets:
        out_prefix = f"{R2_PREFIX}/{sid}/vectors/{index['name']}"
        if r2.head(f"{out_prefix}/manifest.json") is not None:
            continue
        spec = dataclasses.replace(base, name=f"embed-{sid}", input_prefix=f"{R2_PREFIX}/{sid}/embed-job")
        started = time.time()
        result = runner.run(spec, r2, embed_job.make_process(spec, args.executor), executor=args.executor, log=log)
        manifest = runner.finish(spec, r2)
        if not manifest["complete"]:
            log(f"{sid}: embedding incomplete ({result}); run again to resume")
            return 1
        mats, ids = [], []
        for uid in sorted(manifest["units"]):
            z = np.load(io.BytesIO(r2.get(manifest["units"][uid]["key"])))
            mats.append(z["matrix"])
            ids.extend(z["ids"].tolist())
        folder = BUILD / f"vectors-{sid}"
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "matrix.npy", np.vstack(mats))
        np.save(folder / "ids.npy", np.array(ids))
        files = {}
        for name in ("matrix.npy", "ids.npy"):
            meta = r2.put_file(f"{out_prefix}/{name}", folder / name)
            files[name] = meta
        spent = None
        if args.executor == "workers_ai":
            from archive_debugger.audit.budget import Ledger
            ledger = Ledger(REPO / "reports" / "v2" / "scale" / "embed_ledger.jsonl", phase_cap=EMBED_CEILING_USD)
            spent = round(ledger.totals(f"embed-{sid}:run-1").spent, 4)
        r2.put(f"{out_prefix}/manifest.json", json.dumps({"shard_id": sid, "index": index, "rows": len(ids),
                                                          "executor": args.executor, "spent_usd": spent,
                                                          "seconds": round(time.time() - started, 1), "files": files,
                                                          "at": now()}, indent=1).encode("utf-8"))
        shutil.rmtree(folder)
        log(f"{sid}: {len(ids)} vectors ({index['name']}) on R2; spent {spent}")
    return 0


def cmd_status(args) -> int:
    have = fetched()
    state = read_state()
    by_shard = members()
    for s in load_plan():
        ids = by_shard.get(s["shard_id"], [])
        done = sum(1 for i in ids if i in have)
        built = state.get(s["shard_id"])
        print(f"{s['shard_id']:28s} fetched {done:6d}/{len(ids):6d}  " +
              (f"built {built['built_at']} ({built['built_passages']} passages)" if built else "not built"))
    return 0


def cmd_build(args) -> int:
    r2 = store()
    shard = next(s for s in load_plan() if s["shard_id"] == args.shard)
    build_shard(shard, members().get(args.shard, []), fetched(), catalogue_records(), r2, allow_partial=args.allow_partial)
    return 0


def cmd_run(args) -> int:
    r2 = store()
    records = catalogue_records()
    by_shard = members()
    log("shard builder running")
    while True:
        have = fetched()
        state = read_state()
        ready = [s for s in load_plan() if s["shard_id"] not in state
                 and by_shard.get(s["shard_id"]) and all(i in have for i in by_shard[s["shard_id"]])]
        for shard in ready:
            if built_on_r2(r2, shard["shard_id"]):
                log(f"{shard['shard_id']}: already on R2; recorded")
                st = read_state()
                st[shard["shard_id"]] = json.loads(r2.get(f"{R2_PREFIX}/{shard['shard_id']}/manifest.json"))
                write_state(st)
                continue
            build_shard(shard, by_shard[shard["shard_id"]], have, records, r2)
        if args.once:
            return 0
        if len(read_state()) == len(load_plan()):
            log("every shard is built")
            return 0
        time.sleep(POLL_S)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["order", "status", "run", "build", "embed", "estimate"])
    ap.add_argument("--executor", choices=["local", "workers_ai", "k8s"], default="workers_ai")
    ap.add_argument("--shard", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--allow-partial", action="store_true", help="build: with the documents fetched so far")
    args = ap.parse_args(argv)
    return {"order": cmd_order, "status": cmd_status, "run": cmd_run, "build": cmd_build, "embed": cmd_embed,
            "estimate": cmd_estimate}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
