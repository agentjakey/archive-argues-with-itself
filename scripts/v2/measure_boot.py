"""Measure a cold boot step by step inside a container: time and cgroup memory per step.

Run inside the serving image with the data source mounted read-only at --src, an EMPTY volume at
/data, and the network off. It does what a container on a fresh ephemeral disk does, in order, and
records each step's wall time and the container's memory while it runs:

  fetch    copy each enabled scope's files from --src into /data. A stand-in for the R2 download:
           it measures local disk throughput, not R2. The R2 number comes from
           scripts/v2/time_r2_fetch.py, which needs real credentials.
  verify   the boot's own sha256 check (archive_debugger.boot.provision_scope with placeholder R2
           settings, so the present-file path runs and nothing is downloaded).

then one of two modes:

  server     start the real server (uvicorn archive_debugger.api.app:app) and poll /health:
             "listen" ends at the first HTTP answer (the app's startup, which opens every scope,
             loads the embedding model and, with the numpy backend, the resident matrix);
             "warm" ends at the first 200. Then a few stub /ask calls per scope ("asks") and a
             quiet period ("steady"). This is the authoritative empty-disk-to-/health-200 path.
  inprocess  the same startup split into its parts by calling the server's own functions in this
             process: embedder, open, dense, pool, facts, warm, asks, steady. --mmap off skips the
             8 GiB mmap setting so its effect on memory can be measured.

Memory is sampled every 100 ms from the container's cgroup (memory.current and memory.stat:
anon, file, file_mapped) and from the measured process's /proc status (VmRSS, VmHWM). memory.peak
and the oom_kill count are read at each step's end. Prints one JSON document to --out.

    python /harness/measure_boot.py --mode server --scopes both --dense numpy --out /out/run.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
SRC_LAYOUT = {
    "pilot": [("db", "civic.db", "CIVIC_DB_PATH"), ("index", "index/vectors.db", "CIVIC_INDEX_PATH")],
    "microlog": [("db", "microlog/civic_microlog.db", "MICROLOG_DB_PATH"),
                 ("index", "microlog/index/vectors_microlog.db", "MICROLOG_INDEX_PATH")],
}
SEED_FILES = {"pilot": "eval/seed_questions.jsonl", "microlog": "config/seed_questions.microlog.jsonl"}
PORT = 8080


def read_int(path: Path):
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    return None if raw == "max" else int(raw)


def memory_stat() -> dict:
    out = {}
    try:
        for line in (CGROUP / "memory.stat").read_text().splitlines():
            key, value = line.split()
            if key in ("anon", "file", "file_mapped", "shmem", "active_file", "inactive_file"):
                out[key] = int(value)
    except OSError:
        pass
    return out


def oom_kills():
    try:
        for line in (CGROUP / "memory.events").read_text().splitlines():
            key, value = line.split()
            if key == "oom_kill":
                return int(value)
    except OSError:
        pass
    return None


def proc_status(pid: int) -> dict:
    out = {}
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "RssAnon:", "RssFile:")):
                key, value = line.split(":", 1)
                out[key] = int(value.split()[0]) * 1024
    except OSError:
        pass
    return out


class Sampler:
    """Background sampler of cgroup and process memory, keeping per-step maxima."""

    FIELDS = ("current", "anon", "file", "file_mapped", "VmRSS", "RssAnon", "RssFile")

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.pid = os.getpid()
        self._lock = threading.Lock()
        self._max: dict = {}
        self._last: dict = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def watch(self, pid: int) -> None:
        with self._lock:
            self.pid = pid

    def snapshot(self) -> dict:
        snap = {"current": read_int(CGROUP / "memory.current")}
        snap.update(memory_stat())
        with self._lock:
            pid = self.pid
        snap.update(proc_status(pid))
        return snap

    def _run(self) -> None:
        while not self._stop.is_set():
            snap = self.snapshot()
            with self._lock:
                self._last = snap
                for key in self.FIELDS:
                    if snap.get(key) is not None:
                        self._max[key] = max(self._max.get(key, 0), snap[key])
            time.sleep(self.interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def reset_max(self) -> None:
        with self._lock:
            self._max = {}

    def take(self) -> tuple[dict, dict]:
        snap = self.snapshot()
        with self._lock:
            for key in self.FIELDS:
                if snap.get(key) is not None:
                    self._max[key] = max(self._max.get(key, 0), snap[key])
            return dict(self._max), snap


class Steps:
    def __init__(self, sampler: Sampler, t0: float):
        self.sampler = sampler
        self.t0 = t0
        self.rows: list[dict] = []
        self._name = None
        self._start = None

    def begin(self, name: str) -> None:
        self.sampler.reset_max()
        self._name, self._start = name, time.monotonic()
        print(f"[measure] step {name} start at {self._start - self.t0:.1f}s", flush=True)

    def end(self, **extra) -> dict:
        now = time.monotonic()
        maxima, last = self.sampler.take()
        row = {"step": self._name, "seconds": round(now - self._start, 2),
               "elapsed_at_end": round(now - self.t0, 2),
               "max": maxima, "end": last,
               "memory_peak": read_int(CGROUP / "memory.peak"), "oom_kill": oom_kills()}
        row.update(extra)
        self.rows.append(row)
        print(f"[measure] step {self._name} done in {row['seconds']}s "
              f"cg_max_mb={maxima.get('current', 0) / 2**20:.0f} anon_max_mb={maxima.get('anon', 0) / 2**20:.0f}",
              flush=True)
        return row


def scope_list(arg: str) -> list[str]:
    return ["pilot", "microlog"] if arg == "both" else [arg]


def dest_paths(scope: str) -> list[tuple[str, Path, Path]]:
    out = []
    for kind, rel, env in SRC_LAYOUT[scope]:
        out.append((kind, Path(rel), Path(os.environ[env])))
    return out


def fetch(scopes: list[str], src: Path) -> dict:
    copied = {}
    for scope in scopes:
        for kind, rel, dest in dest_paths(scope):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, dest)        # no copystat: a fresh download gets a new mtime too
            copied[f"{scope}/{kind}"] = dest.stat().st_size
    return copied


def verify(scopes: list[str]) -> dict:
    """The boot's present-file sha256 path, per scope, without a download."""
    from archive_debugger import boot, scopes as scope_mod
    os.environ.setdefault("R2_ENDPOINT", "http://127.0.0.1:9")        # placeholders: present files only
    os.environ.setdefault("R2_BUCKET", "measure")
    os.environ.setdefault("R2_ACCESS_KEY_ID", "measure")
    os.environ.setdefault("R2_SECRET_ACCESS_KEY", "measure")
    registry = scope_mod.load_registry()
    out = {}

    def no_client():
        raise RuntimeError("verify must not download: a file was missing or its hash did not match")

    for scope in scopes:
        specs = boot.scope_provision_specs(scope, registry=registry)
        t = time.monotonic()
        boot.provision_scope(specs, lambda m: None, get_client=no_client)
        out[scope] = round(time.monotonic() - t, 2)
    return out


def data_disk() -> dict:
    usage = shutil.disk_usage("/data")
    files = sum(p.stat().st_size for p in Path("/data").rglob("*") if p.is_file())
    return {"data_files_bytes": files, "volume_used_bytes": usage.used}


def load_seed(scope: str, limit: int) -> list[dict]:
    rows = []
    for line in Path(SEED_FILES[scope]).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows[:limit]


def latency_summary(row: dict) -> dict:
    """Median, max and the raw list of one scope's ask latencies, with any limited-mode reasons."""
    values = sorted(row["latencies"])
    row["median"] = values[len(values) // 2] if values else None
    row["max"] = values[-1] if values else None
    row["degraded"] = len(row["degraded_reasons"])
    return row


def http_get(url: str, timeout: float = 60.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


# --- server mode ---------------------------------------------------------------------------------

def run_server(args, steps: Steps, sampler: Sampler, scopes: list[str]) -> dict:
    env = dict(os.environ)
    env["CIVIC_DENSE_BACKEND"] = args.dense
    env["CIVIC_ENABLED_SCOPES"] = ",".join(scopes)
    if args.guard == "anon":
        override = str(Path(__file__).resolve().parent / "guard_anon")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = override + os.pathsep + existing if existing else override
    if scopes == ["microlog"]:
        env["CIVIC_SCOPE"] = "microlog"
    for key in ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        env.pop(key, None)
    log_path = Path(args.out).with_suffix(".server.log")
    log_fh = open(log_path, "w", encoding="utf-8")
    steps.begin("listen")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "archive_debugger.api.app:app",
                             "--host", "127.0.0.1", "--port", str(PORT)],
                            stdout=log_fh, stderr=subprocess.STDOUT, env=env)
    sampler.watch(proc.pid)
    base = f"http://127.0.0.1:{PORT}"
    status = None
    died = None
    while True:
        if proc.poll() is not None:
            died = proc.returncode
            break
        try:
            status, _ = http_get(base + "/health", timeout=5)
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            status = None
        if status is not None:
            break
        time.sleep(0.25)
    steps.end(first_status=status, exited=died)
    result = {"server_exit": died}
    if died is None:
        steps.begin("warm")
        while status != 200:
            if proc.poll() is not None:
                died = proc.returncode
                break
            try:
                status, _ = http_get(base + "/health", timeout=5)
            except urllib.error.HTTPError as exc:
                status = exc.code
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                status = None
            time.sleep(0.25)
        steps.end(status=status, exited=died)
        result["server_exit"] = died
    if died is None:
        steps.begin("asks")
        latencies = []
        failures = 0
        degraded = 0     # a 200 in limited mode (e.g. retrieval past its deadline) is not a served answer
        by_scope = {}
        for scope in scopes:
            scope_row = {"latencies": [], "degraded_reasons": []}
            for q in load_seed(scope, args.asks):
                params = urllib.parse.urlencode({"q": q["text"], "provider": "stub", "nocache": 1, "scope": scope})
                t = time.monotonic()
                try:
                    code, body = http_get(f"{base}/ask?{params}", timeout=60)
                    reason = json.loads(body).get("degraded") if code == 200 else None
                    if reason:
                        degraded += 1
                        scope_row["degraded_reasons"].append(reason.get("reason") if isinstance(reason, dict) else str(reason))
                except Exception:  # noqa: BLE001 - a failed ask is counted, not fatal to the measurement
                    code = None
                latency = round(time.monotonic() - t, 3)
                latencies.append(latency)
                scope_row["latencies"].append(latency)
                failures += code != 200
            by_scope[scope] = latency_summary(scope_row)
        steps.end(asks=len(latencies), failures=failures, degraded=degraded,
                  latency_median=sorted(latencies)[len(latencies) // 2] if latencies else None,
                  latency_max=max(latencies) if latencies else None, by_scope=by_scope)
        steps.begin("steady")
        time.sleep(args.steady)
        steps.end()
        result["server_exit"] = proc.poll()
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    log_fh.close()
    result["server_log_tail"] = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    return result


# --- in-process mode -----------------------------------------------------------------------------

def run_inprocess(args, steps: Steps, scopes: list[str]) -> dict:
    os.environ["CIVIC_DENSE_BACKEND"] = "sqlite"     # open without the resident load; "dense" does it
    from archive_debugger import scopes as scope_mod
    from archive_debugger.api import app as app_mod
    from archive_debugger.api.cache import retrieval_fingerprint
    from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool
    from archive_debugger.retrieve import dense
    from archive_debugger.retrieve.config import load_retrieve_config
    from archive_debugger.retrieve.embed import make_embedder
    from archive_debugger.retrieve.search import Retriever

    built = {}
    embedder = None
    for scope in scopes:
        resolved = scope_mod.resolve_scope(scope)
        active = None if resolved.inherit else resolved
        with scope_mod.activate(active):
            cfg_path = Path(resolved.config_path)
            cfg = load_retrieve_config(cfg_path)
            if embedder is None:
                steps.begin("embedder")
                embedder = make_embedder(cfg.embedder, cfg.embedding_model, cfg.embedding_dim)
                steps.end(model=cfg.embedding_model)
            steps.begin(f"open:{scope}")
            base = Retriever(cfg_path, embedder=embedder, cfg=cfg)
            steps.end()
            if args.dense == "numpy":
                steps.begin(f"dense:{scope}")
                os.environ["CIVIC_DENSE_BACKEND"] = "numpy"
                base.dense_index = dense.load_if_enabled(base.conn)
                os.environ["CIVIC_DENSE_BACKEND"] = "sqlite"
                steps.end(loaded=base.dense_index is not None,
                          rows=getattr(base.dense_index, "n", None))
            steps.begin(f"pool:{scope}")
            if args.mmap == "on":
                app_mod._enable_mmap(base.conn)
            locked = app_mod._LockedEmbedder(embedder)
            pool = []
            for _ in range(app_mod.POOL_SIZE):
                r = Retriever(cfg_path, embedder=locked, cfg=cfg, dense_index=base.dense_index)
                if args.mmap == "on":
                    app_mod._enable_mmap(r.conn)
                pool.append(r)
            steps.end(pool_size=len(pool),
                      shared_dense=all(r.dense_index is base.dense_index for r in pool))
            steps.begin(f"facts:{scope}")
            gcfg = load_generate_config(cfg_path)
            retrieval_fingerprint(base.cfg)
            corpus = app_mod.corpus_facts(base.conn, app_mod._pilot_window(cfg_path))
            app_mod.scope_facts(scope, cfg_path, corpus)
            app_mod.scope_composition(base.conn, corpus)
            steps.end()
            built[scope] = (base, pool, gcfg)
    for scope in scopes:
        base, pool, gcfg = built[scope]
        steps.begin(f"warm:{scope}")
        app_mod._warm(pool[0].conn)
        retrieve_pool(pool[0], app_mod.WARM_QUERY, build_filters(None), gcfg["top_k"])
        steps.end()
    steps.begin("asks")
    latencies = []
    by_scope = {}
    for scope in scopes:
        base, pool, gcfg = built[scope]
        scope_row = {"latencies": [], "degraded_reasons": []}
        for q in load_seed(scope, args.asks):
            t = time.monotonic()
            retrieve_pool(pool[0], q["text"], build_filters(q.get("filters")), gcfg["top_k"])
            latency = round(time.monotonic() - t, 3)
            latencies.append(latency)
            scope_row["latencies"].append(latency)
        by_scope[scope] = latency_summary(scope_row)
    steps.end(asks=len(latencies), latency_median=sorted(latencies)[len(latencies) // 2] if latencies else None,
              latency_max=max(latencies) if latencies else None, by_scope=by_scope)
    steps.begin("steady")
    time.sleep(args.steady)
    steps.end()
    return {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["server", "inprocess"], required=True)
    parser.add_argument("--scopes", choices=["pilot", "microlog", "both"], required=True)
    parser.add_argument("--dense", choices=["sqlite", "numpy"], required=True)
    parser.add_argument("--mmap", choices=["on", "off"], default="on", help="inprocess mode only")
    parser.add_argument("--guard", choices=["rss", "anon"], default="rss",
                        help="server mode: anon loads scripts/v2/guard_anon (measurement-only guard override)")
    parser.add_argument("--src", default="/src")
    parser.add_argument("--asks", type=int, default=10, help="seed questions per scope after warm")
    parser.add_argument("--steady", type=float, default=15.0, help="quiet seconds sampled at the end")
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    scopes = scope_list(args.scopes)
    if any(Path("/data").iterdir()):
        print("refusing to run: /data is not empty (a cold boot starts from an empty disk)", file=sys.stderr)
        return 2
    sampler = Sampler()
    sampler.start()
    t0 = time.monotonic()
    steps = Steps(sampler, t0)
    record = {"label": args.label, "mode": args.mode, "scopes": scopes, "dense": args.dense, "mmap": args.mmap,
              "guard": args.guard,
              "memory_max": read_int(CGROUP / "memory.max"), "cpus": os.cpu_count(),
              "kernel": platform.release(), "python": platform.python_version(),
              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        steps.begin("fetch")
        record["fetched_bytes"] = fetch(scopes, Path(args.src))
        steps.end(stand_in="local volume copy, not R2")
        steps.begin("verify")
        record["verify_seconds_by_scope"] = verify(scopes)
        steps.end()
        if args.mode == "server":
            record.update(run_server(args, steps, sampler, scopes))
        else:
            record.update(run_inprocess(args, steps, scopes))
        record["disk"] = data_disk()
        asks = next((r for r in steps.rows if r["step"] == "asks"), None)
        record["ok"] = (record.get("server_exit") is None
                        and all(r.get("oom_kill") in (0, None) for r in steps.rows)
                        and asks is not None and not asks.get("failures") and not asks.get("degraded"))
    except Exception as exc:  # noqa: BLE001 - record the failure with the steps measured so far
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["ok"] = False
    finally:
        sampler.stop()
        record["steps"] = steps.rows
        record["total_seconds_to_ready"] = next(
            (r["elapsed_at_end"] for r in steps.rows if r["step"] in ("warm",) and r.get("status") == 200), None)
        record["memory_peak_final"] = read_int(CGROUP / "memory.peak")
        record["oom_kill_final"] = oom_kills()
        Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"[measure] ok={record['ok']} wrote {args.out}", flush=True)
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
