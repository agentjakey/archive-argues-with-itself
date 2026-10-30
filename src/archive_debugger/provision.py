"""Data provisioning for a container that starts on an empty disk (Phase 1, Cloudflare).

The server opens its port first and calls provision() from a background thread, so it can report
progress while the data arrives. For each enabled scope it puts the scope's files on their resolved
paths and checks every file against the sha256 published in config/scopes.toml before anything is
served from it.

Files: the corpus database always. With the numpy dense backend and published dense artifacts
(retrieve/dense.py), the three artifact files replace the 1.6 GB and 2.4 GB vectors databases: a
small empty stand-in index is written in their place, with a sidecar naming the published index it
stands in for, so the dense leg comes only from the byte-identical artifacts. The full vectors
database is fetched instead when the backend is sqlite or a scope has no artifacts.

Sources (CIVIC_PROVISION):
  r2-binding  ranged HTTP GETs to the engine Worker's R2 binding, reached through the container's
              outbound interception (CIVIC_R2_PROXY_URL, default http://r2.internal). No R2 keys
              in the container.
  r2-s3       ranged GETs on R2's S3 API with a read-only, bucket-scoped key pair (R2_* variables).
  present     the files are already on disk (baked into the image, restored from a snapshot, or a
              development machine). Nothing is fetched.

Downloads: every file is split into parts that a pool of threads fetches in parallel and writes at
their offsets. One hashing thread per file reads the file back in order as soon as a contiguous
prefix has arrived, from the page cache those writes just filled, so hashing runs alongside the
download and there is no separate verification pass. A file whose hash does not match is deleted and
provisioning fails: the server never serves a scope from an unverified file.

Files already present: CIVIC_VERIFY_PRESENT=full (default) hashes them; trust-image skips the hash
for files that are part of the container image, whose layers the registry verifies by digest on
pull (docs/SELF_HOSTING.md, "Design choices").

One retry rule for every network read: timeouts, connection errors, 5xx, 408 and 429 are retried
with backoff; any other 4xx fails at once.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from archive_debugger import scopes

ENV_PROVISION = "CIVIC_PROVISION"
ENV_PROXY_URL = "CIVIC_R2_PROXY_URL"
ENV_VERIFY_PRESENT = "CIVIC_VERIFY_PRESENT"
ENV_WORKERS = "CIVIC_PROVISION_WORKERS"
ENV_PART_MB = "CIVIC_PROVISION_PART_MB"
DEFAULT_PROXY_URL = "http://r2.internal"
DEFAULT_WORKERS = 16
DEFAULT_PART_MB = 32
HASH_CHUNK = 8 * 1024 * 1024
RETRY_STATUSES = {408, 429}
MAX_ATTEMPTS = 6

Log = Callable[[str], None]


class ProvisionError(RuntimeError):
    """A file could not be provisioned or verified; nothing from that scope may be served."""


class Stopped(RuntimeError):
    """Provisioning was asked to stop (the container is shutting down)."""


@dataclass
class Job:
    scope: str
    kind: str                 # db, index, dense_matrix, dense_ids, dense_manifest
    key: str                  # R2 object key
    dest: Path
    sha256: str


@dataclass
class Plan:
    jobs: list = field(default_factory=list)
    stubs: list = field(default_factory=list)   # (stub index path, published index sha256)


class Progress:
    """Thread-safe provisioning state for /health: a stage, per-file byte counts, any error."""

    def __init__(self):
        self._lock = threading.Lock()
        self.stage = "starting"
        self.files: dict = {}
        self.error: Optional[str] = None
        self.started = time.monotonic()
        self.finished: Optional[float] = None

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self.stage = stage

    def add_file(self, name: str, total: int) -> None:
        with self._lock:
            self.files[name] = {"bytes": 0, "total": total, "hashed": 0, "state": "queued"}

    def advance(self, name: str, *, downloaded: int = 0, hashed: int = 0, state: Optional[str] = None) -> None:
        with self._lock:
            row = self.files[name]
            row["bytes"] += downloaded
            row["hashed"] += hashed
            if state:
                row["state"] = state

    def fail(self, message: str) -> None:
        with self._lock:
            self.error = message
            self.stage = "failed"

    def done(self) -> None:
        with self._lock:
            self.finished = time.monotonic()

    def snapshot(self) -> dict:
        with self._lock:
            total = sum(f["total"] for f in self.files.values())
            got = sum(f["bytes"] for f in self.files.values())
            hashed = sum(f["hashed"] for f in self.files.values())
            end = self.finished or time.monotonic()
            return {"stage": self.stage, "error": self.error, "files": len(self.files),
                    "bytes_total": total, "bytes_downloaded": got, "bytes_verified": hashed,
                    "seconds": round(end - self.started, 1)}


# --- sources ------------------------------------------------------------------------------------

class RangeSource(Protocol):
    def size(self, key: str) -> int: ...
    def read(self, key: str, start: int, end: int) -> bytes: ...


def _s3_status(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    return response.get("ResponseMetadata", {}).get("HTTPStatusCode")


def _retrying(fn, what: str, stop: threading.Event):
    """Run fn with the one retry rule; raise ProvisionError when it gives up."""
    delay = 1.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if stop.is_set():
            raise Stopped(what)
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code not in RETRY_STATUSES:
                raise ProvisionError(f"{what}: HTTP {exc.code}") from exc
            last = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last = type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - an S3 client error carries its HTTP status
            status = _s3_status(exc)
            if status is not None and status < 500 and status not in RETRY_STATUSES:
                raise ProvisionError(f"{what}: status {status}") from exc
            last = type(exc).__name__
        if attempt < MAX_ATTEMPTS:
            stop.wait(delay)
            delay = min(delay * 2, 16.0)
    raise ProvisionError(f"{what}: gave up after {MAX_ATTEMPTS} attempts ({last})")


class HttpRangeSource:
    """R2 through the engine Worker's binding: GET <base>/<key> with a Range header, HEAD for size."""

    def __init__(self, base_url: str, *, timeout_s: float = 60.0, stop: Optional[threading.Event] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.stop = stop or threading.Event()

    def _url(self, key: str) -> str:
        return f"{self.base_url}/{urllib.request.quote(key)}"

    def size(self, key: str) -> int:
        def head():
            req = urllib.request.Request(self._url(key), method="HEAD")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return int(resp.headers["Content-Length"])
        return _retrying(head, f"size of {key}", self.stop)

    def read(self, key: str, start: int, end: int) -> bytes:
        def get():
            req = urllib.request.Request(self._url(key), headers={"Range": f"bytes={start}-{end - 1}"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read()
            if len(body) != end - start:
                raise ConnectionError(f"short read {len(body)} of {end - start}")
            return body
        return _retrying(get, f"{key} bytes {start}-{end - 1}", self.stop)


class S3RangeSource:
    """R2 through its S3 API with a read-only key pair (boot.make_r2_client)."""

    def __init__(self, client, bucket: str, *, stop: Optional[threading.Event] = None):
        self.client = client
        self.bucket = bucket
        self.stop = stop or threading.Event()

    def size(self, key: str) -> int:
        return _retrying(lambda: int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]),
                         f"size of {key}", self.stop)

    def read(self, key: str, start: int, end: int) -> bytes:
        def get():
            body = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end - 1}")["Body"].read()
            if len(body) != end - start:
                raise ConnectionError(f"short read {len(body)} of {end - start}")
            return body
        return _retrying(get, f"{key} bytes {start}-{end - 1}", self.stop)


# --- the plan ----------------------------------------------------------------------------------

def dense_backend_numpy() -> bool:
    return os.environ.get("CIVIC_DENSE_BACKEND", "sqlite").strip().lower() == "numpy"


def plan_scope(name: str, registry: dict, *, numpy_backend: bool) -> Plan:
    """The files one scope needs: its release files (archive_debugger.release_files, from the scope
    registry alone) placed on the scope's resolved paths. With the numpy backend and published dense
    artifacts, the artifacts replace the vectors database, which gets a stand-in."""
    from archive_debugger import release_files
    from archive_debugger.retrieve import dense
    try:
        files = {f.kind: f for f in release_files.scope_files(name, registry)}
    except release_files.ReleaseError as exc:
        raise ProvisionError(str(exc)) from exc
    resolved = scopes.resolve_scope(name)
    db_path, index_path = Path(resolved.db_path), Path(resolved.index_path)
    artifacts = dense.artifact_paths(index_path)
    destination = {"db": db_path, "index": index_path, "dense_matrix": artifacts["matrix"],
                   "dense_ids": artifacts["ids"], "dense_manifest": artifacts["manifest"],
                   "facts": release_files.facts_path(db_path)}
    use_artifacts = numpy_backend and "dense_matrix" in files
    plan = Plan()
    for kind, f in files.items():
        if kind.startswith("dense_") and not use_artifacts:
            continue
        if kind == "index" and use_artifacts:
            plan.stubs.append((index_path, f.sha256))
            continue
        plan.jobs.append(Job(name, kind, f.key, destination[kind], f.sha256))
    return plan


def write_stub_index(path: Path, published_sha256: str) -> None:
    """An empty vectors database (the passages_vec and index_meta tables, no rows) plus a sidecar
    naming the published index it stands in for. The dense leg then comes only from the artifacts;
    retrieve/dense.py accepts the artifacts for this stub only when the sidecar's sha256 is the
    one their manifest was built from."""
    import sqlite3
    from archive_debugger.retrieve import dense
    from archive_debugger.retrieve.index import VEC_SCHEMA
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(str(tmp))
    conn.executescript(VEC_SCHEMA)
    conn.commit()
    conn.close()
    tmp.replace(path)
    dense.stub_sidecar(path).write_text(json.dumps({"stands_in_for_index_sha256": published_sha256}) + "\n",
                                        encoding="utf-8")


# --- fetching ----------------------------------------------------------------------------------

def hash_file(path: Path, progress: Optional[Progress], name: str, stop: threading.Event) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            if stop.is_set():
                raise Stopped(name)
            block = fh.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
            if progress is not None:
                progress.advance(name, hashed=len(block))
    return digest.hexdigest()


class _FileFetch:
    """One file in flight: its .part file, which parts have landed, and the in-order hasher."""

    def __init__(self, job: Job, size: int, part_size: int, progress: Progress, stop: threading.Event):
        self.job = job
        self.size = size
        self.part_size = part_size
        self.parts = max(1, -(-size // part_size))
        self.progress = progress
        self.stop = stop
        self.name = f"{job.scope}/{job.kind}"
        self.part_path = job.dest.with_name(job.dest.name + ".part")
        job.dest.parent.mkdir(parents=True, exist_ok=True)
        with open(self.part_path, "wb") as fh:
            fh.truncate(size)
        self.fd = os.open(self.part_path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        self._write_lock = threading.Lock()
        self._landed = [False] * self.parts
        self._cond = threading.Condition()
        self.failed: Optional[BaseException] = None
        self.digest: Optional[str] = None
        self.hasher = threading.Thread(target=self._hash_in_order, name=f"hash-{self.name}", daemon=True)

    def write(self, index: int, data: bytes) -> None:
        offset = index * self.part_size
        if hasattr(os, "pwrite"):
            os.pwrite(self.fd, data, offset)
        else:                                   # Windows (development only): serialize seek + write
            with self._write_lock:
                os.lseek(self.fd, offset, os.SEEK_SET)
                os.write(self.fd, data)
        self.progress.advance(self.name, downloaded=len(data))
        with self._cond:
            self._landed[index] = True
            self._cond.notify_all()

    def abort(self, exc: BaseException) -> None:
        with self._cond:
            if self.failed is None:
                self.failed = exc
            self._cond.notify_all()

    def _hash_in_order(self) -> None:
        digest = hashlib.sha256()
        position = 0
        next_part = 0
        try:
            with open(self.part_path, "rb") as reader:
                while next_part < self.parts:
                    with self._cond:
                        while not self._landed[next_part] and self.failed is None and not self.stop.is_set():
                            self._cond.wait(timeout=1.0)
                        if self.failed is not None or self.stop.is_set():
                            return
                        ready_until = next_part
                        while ready_until < self.parts and self._landed[ready_until]:
                            ready_until += 1
                    end = min(ready_until * self.part_size, self.size)
                    reader.seek(position)
                    while position < end:
                        block = reader.read(min(HASH_CHUNK, end - position))
                        if not block:
                            raise ProvisionError(f"{self.name}: file shorter than expected at {position}")
                        digest.update(block)
                        position += len(block)
                        self.progress.advance(self.name, hashed=len(block))
                    next_part = ready_until
            self.digest = digest.hexdigest()
        except BaseException as exc:  # noqa: BLE001 - reported to the caller through failed
            self.abort(exc)

    def finish(self) -> None:
        self.hasher.join()
        os.close(self.fd)
        if self.failed is not None:
            self.part_path.unlink(missing_ok=True)
            raise self.failed
        if self.stop.is_set():
            raise Stopped(self.name)
        if self.digest != self.job.sha256:
            self.part_path.unlink(missing_ok=True)
            raise ProvisionError(f"{self.name}: sha256 mismatch for {self.job.key} "
                                 f"(got {str(self.digest)[:16]}..., expected {self.job.sha256[:16]}...); removed")
        self.part_path.replace(self.job.dest)
        self.progress.advance(self.name, state="verified")


def fetch_all(jobs: list, source: RangeSource, progress: Progress, *, workers: int, part_size: int,
              stop: threading.Event, log: Log = print) -> None:
    """Download every job in parallel ranged parts, hashing each file in order as it arrives."""
    if not jobs:
        return
    fetches = []
    for job in jobs:
        size = source.size(job.key)
        progress.add_file(f"{job.scope}/{job.kind}", size)
        fetches.append(_FileFetch(job, size, part_size, progress, stop))
    work: queue.Queue = queue.Queue()
    longest = max(f.parts for f in fetches)
    for index in range(longest):                 # round-robin across files so all of them advance
        for f in fetches:
            if index < f.parts:
                work.put((f, index))
    for f in fetches:
        f.hasher.start()
        progress.advance(f.name, state="downloading")
    errors: list = []

    def worker():
        while not stop.is_set() and not errors:
            try:
                f, index = work.get_nowait()
            except queue.Empty:
                return
            start = index * f.part_size
            end = min(start + f.part_size, f.size)
            try:
                f.write(index, source.read(f.job.key, start, end))
            except BaseException as exc:  # noqa: BLE001 - stop everything on the first failure
                errors.append(exc)
                for other in fetches:
                    other.abort(exc)
                return

    threads = [threading.Thread(target=worker, name=f"fetch-{i}", daemon=True) for i in range(max(1, workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if stop.is_set():
        for f in fetches:
            f.abort(Stopped(f.name))
    problems = []
    for f in fetches:
        try:
            f.finish()
        except BaseException as exc:  # noqa: BLE001 - collect, then raise the first
            problems.append(exc)
    if errors or problems:
        first = (errors or problems)[0]
        raise first if isinstance(first, (ProvisionError, Stopped)) else ProvisionError(str(first))
    log(f"[provision] {len(fetches)} files downloaded and verified")


def _verify_present(jobs: list, progress: Progress, stop: threading.Event, policy: str, log: Log) -> list:
    """Jobs whose file is already present are checked (or trusted, for image data) and dropped from
    the list; the rest still need fetching."""
    missing = []
    for job in jobs:
        if not job.dest.exists():
            missing.append(job)
            continue
        name = f"{job.scope}/{job.kind}"
        progress.add_file(name, job.dest.stat().st_size)
        progress.advance(name, downloaded=job.dest.stat().st_size, state="present")
        if policy == "trust-image":
            progress.advance(name, state="trusted (image)")
            continue
        got = hash_file(job.dest, progress, name, stop)
        if got != job.sha256:
            raise ProvisionError(f"{name}: present file {job.dest} does not match the published sha256")
        progress.advance(name, state="verified")
    if len(missing) != len(jobs):
        log(f"[provision] {len(jobs) - len(missing)} files already present ({policy})")
    return missing


def make_source(mode: str, stop: threading.Event) -> Optional[RangeSource]:
    if mode == "r2-binding":
        return HttpRangeSource(os.environ.get(ENV_PROXY_URL) or DEFAULT_PROXY_URL, stop=stop)
    if mode == "r2-s3":
        from archive_debugger.boot import make_r2_client
        return S3RangeSource(make_r2_client(), os.environ["R2_BUCKET"], stop=stop)
    if mode == "present":
        return None
    raise ProvisionError(f"unknown {ENV_PROVISION}={mode!r} (r2-binding, r2-s3 or present)")


def provision(scope_names: list, progress: Progress, *, stop: threading.Event, log: Log = print,
              registry: Optional[dict] = None, source: Optional[RangeSource] = None,
              mode: Optional[str] = None) -> None:
    """Provision and verify every file the given scopes need. Raises ProvisionError (or Stopped)."""
    mode = mode or os.environ.get(ENV_PROVISION, "present").strip().lower()
    policy = os.environ.get(ENV_VERIFY_PRESENT, "full").strip().lower()
    if policy not in ("full", "trust-image"):
        raise ProvisionError(f"unknown {ENV_VERIFY_PRESENT}={policy!r} (full or trust-image)")
    reg = registry if registry is not None else scopes.load_registry()
    numpy_backend = dense_backend_numpy()
    jobs, stubs = [], []
    for name in scope_names:
        plan = plan_scope(name, reg, numpy_backend=numpy_backend)
        jobs += plan.jobs
        stubs += plan.stubs
    progress.set_stage("checking")
    missing = _verify_present(jobs, progress, stop, policy, log)
    if missing:
        source = source or make_source(mode, stop)
        if source is None:
            raise ProvisionError("files missing and nothing to fetch them from (CIVIC_PROVISION=present): "
                                 + ", ".join(str(j.dest) for j in missing))
        progress.set_stage("downloading")
        workers = int(os.environ.get(ENV_WORKERS) or DEFAULT_WORKERS)
        part_size = int(os.environ.get(ENV_PART_MB) or DEFAULT_PART_MB) * 1024 * 1024
        fetch_all(missing, source, progress, workers=workers, part_size=part_size, stop=stop, log=log)
    from archive_debugger.retrieve import dense
    for index_path, published in stubs:
        # A real index already on disk (a development machine) is kept; otherwise the stand-in.
        real_index = Path(index_path).exists() and dense.stub_target(Path(index_path)) is None
        if not real_index:
            write_stub_index(Path(index_path), published)
    progress.set_stage("provisioned")
    progress.done()
