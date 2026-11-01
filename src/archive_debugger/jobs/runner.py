"""Running a job's units, resuming, and the manifest.

Inputs: <input_prefix>/units.jsonl, one unit per line ({"id", ...}), written by the job's prepare
step together with each unit's input files. Its sha256 is the input fingerprint.
Outputs: <run_prefix>/units/<id>.<ext>, then <run_prefix>/units/<id>.done.json naming the output's
sha256, size, executor, model and times. A unit is done only when its done file exists and the
output it names has that sha256: a crash between the two leaves the unit to be run again, and running
it again writes the same key. Workers split units by index (worker i of n takes every unit whose
position mod n is i), which is how a Kubernetes Indexed Job's JOB_COMPLETION_INDEX shares the work.
<run_prefix>/manifest.json lists every unit's output once all are done; `verify` checks it."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from archive_debugger.jobs.spec import JobSpec
from archive_debugger.jobs.store import Store, sha256_bytes

UNITS = "units.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_units(store: Store, spec: JobSpec) -> tuple:
    raw = store.get(f"{spec.input_prefix.rstrip('/')}/{UNITS}")
    units = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    ids = [u["id"] for u in units]
    if len(set(ids)) != len(ids):
        raise ValueError("unit ids must be unique")
    return units, sha256_bytes(raw)


def unit_done(store: Store, run_prefix: str, unit_id: str) -> Optional[dict]:
    head = store.head(f"{run_prefix}/units/{unit_id}.done.json")
    if head is None:
        return None
    done = json.loads(store.get(f"{run_prefix}/units/{unit_id}.done.json"))
    out = store.head(done["key"])
    if out is None or (out.get("sha256") and out["sha256"] != done["sha256"]):
        return None
    return done


def run(spec: JobSpec, store: Store, process: Callable, *, executor: str, worker: int = 0, workers: int = 1,
        limit: Optional[int] = None, log: Callable[[str], None] = print) -> dict:
    """Process this worker's share of the units that are not done. `process(unit, store, spec)`
    returns (data: bytes, extension: str, meta: dict)."""
    units, fingerprint = read_units(store, spec)
    prefix = spec.run_prefix(fingerprint)
    mine = [u for n, u in enumerate(units) if n % workers == worker]
    done = skipped = failed = 0
    for unit in mine:
        if limit is not None and done >= limit:
            break
        if unit_done(store, prefix, unit["id"]):
            skipped += 1
            continue
        started = time.time()
        try:
            data, ext, meta = process(unit, store, spec)
        except Exception as exc:       # one failed unit is reported, and the others go on
            failed += 1
            log(f"[{spec.name}] unit {unit['id']} failed: {type(exc).__name__}: {str(exc)[:300]}")
            continue
        key = f"{prefix}/units/{unit['id']}.{ext}"
        stored = store.put(key, data)
        record = {"unit": unit["id"], "key": key, "sha256": stored["sha256"], "bytes": stored["bytes"],
                  "executor": executor, "seconds": round(time.time() - started, 3), "finished_at": now(), **meta}
        store.put(f"{prefix}/units/{unit['id']}.done.json", json.dumps(record, sort_keys=True).encode("utf-8"))
        done += 1
        log(f"[{spec.name}] {unit['id']} done in {record['seconds']} s ({stored['bytes']} bytes)")
    return {"run_prefix": prefix, "units": len(units), "mine": len(mine), "done": done, "skipped": skipped,
            "failed": failed}


def finish(spec: JobSpec, store: Store) -> dict:
    """Write the manifest when every unit is done; otherwise report what is missing."""
    units, fingerprint = read_units(store, spec)
    prefix = spec.run_prefix(fingerprint)
    entries, missing = {}, []
    for unit in units:
        done = unit_done(store, prefix, unit["id"])
        if done is None:
            missing.append(unit["id"])
        else:
            entries[unit["id"]] = {k: done[k] for k in ("key", "sha256", "bytes", "executor")} | \
                                  {k: done[k] for k in ("model", "backend") if k in done}
    manifest = {"job": spec.name, "kind": spec.kind, "code_version": spec.code_version,
                "build_key": spec.build_key(fingerprint), "input_fingerprint": fingerprint,
                "model": spec.model, "params": spec.params, "units": entries, "complete": not missing,
                "missing": missing, "written_at": now(), "store": store.describe()}
    if not missing:
        store.put(f"{prefix}/manifest.json", json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
    return manifest


def verify(spec: JobSpec, store: Store) -> list:
    """Every problem with a finished run: a missing manifest, a missing output, a changed checksum."""
    units, fingerprint = read_units(store, spec)
    prefix = spec.run_prefix(fingerprint)
    if store.head(f"{prefix}/manifest.json") is None:
        return [f"{prefix}/manifest.json is missing"]
    manifest = json.loads(store.get(f"{prefix}/manifest.json"))
    problems = []
    if set(manifest["units"]) != {u["id"] for u in units}:
        problems.append("the manifest does not list exactly the job's units")
    for uid, entry in manifest["units"].items():
        head = store.head(entry["key"])
        if head is None:
            problems.append(f"{uid}: output {entry['key']} is missing")
        elif sha256_bytes(store.get(entry["key"])) != entry["sha256"]:
            problems.append(f"{uid}: output {entry['key']} does not match its sha256")
    return problems
