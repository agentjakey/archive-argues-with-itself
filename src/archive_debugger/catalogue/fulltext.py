"""Full-text fetch for the whole collection: OCR text only, page by page.

For each item the fetcher takes two files the Internet Archive derives from its OCR:
  <name>_hocr_searchtext.txt.gz   the plain text, already gzip-compressed
  <name>_hocr_pageindex.json.gz   for each page, the character offsets of its text in the search text
Together they give each page's own text (the plain _djvu.txt files carry no page breaks). The file
names usually start with the identifier; when they do not, the item's metadata names them. Items
with neither file fall back to <name>_djvu.txt, marked as having no page breaks.

Each item's files are kept as fetched under the local folder, uploaded to the private R2 bucket
under fulltext/v1/<identifier>/, and recorded in manifest.jsonl with their sha256 and size. A
stopped fetch resumes after the last recorded item; an item is never fetched twice. Requests are
polite (net.py: identified, at most two at a time, a pause after each, backoff) and the whole fetch
stops with a report when 429 or 503 responses pile up.

On the cloud runners (GitHub Actions, scripts/v2/catalogue.py fulltext --stream) nothing is kept on
disk but the manifest: each item's files go straight to R2, the fetch order comes from R2
(_state/order.txt), the manifest is restored from its R2 chunks at the start, and status.json is
copied to _state/status.json at every sync, which `catalogue.py status --r2` reads."""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.catalogue import net

DOWNLOAD = "https://archive.org/download/{ident}/{name}"
METADATA = "https://archive.org/metadata/{ident}"
SEARCHTEXT = "_hocr_searchtext.txt.gz"
PAGEINDEX = "_hocr_pageindex.json.gz"
DJVU = "_djvu.txt"
# Which scanned leaves the viewer shows, and their printed numbers. The page index counts every
# scanned leaf; archive.org's page links (/page/n<k>) count only the shown ones, so a page's link
# number comes from this file (measured on pilot items: hOCR page p was corpus leaf p - 1, the
# first scan being a colour card the viewer skips).
PAGE_NUMBERS = "_page_numbers.json"
R2_PREFIX = "fulltext/v1"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def done_identifiers(manifest: Path) -> set:
    if not manifest.exists():
        return set()
    out = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                continue          # a line cut short by a stop: the item is fetched again
            if row.get("kind") != "error":
                out.add(row["identifier"])      # an item that failed is tried again on the next run
    return out


def _try(get: Callable, ident: str, name: str, refusals) -> Optional[bytes]:
    try:
        return get(DOWNLOAD.format(ident=ident, name=name), refusals=refusals)
    except net.HttpError as exc:
        if exc.status in (403, 404):
            return None
        raise


def fetch_item(ident: str, get: Callable, refusals) -> dict:
    """{identifier, kind, files: {role: (name, bytes)}}; kind "no_text" when the item has no OCR.
    When the files are not named after the identifier, the item's metadata names them, and it is
    kept too, compressed, for its page and file lists."""
    import gzip
    # Most items name their files after the identifier: two requests, no metadata call.
    text = _try(get, ident, ident + SEARCHTEXT, refusals)
    if text is not None:
        files = {"searchtext": (ident + SEARCHTEXT, text)}
        index = _try(get, ident, ident + PAGEINDEX, refusals)
        if index is not None:
            files["pageindex"] = (ident + PAGEINDEX, index)
            numbers = _try(get, ident, ident + PAGE_NUMBERS, refusals)
            if numbers is not None:
                files["page_numbers"] = (ident + PAGE_NUMBERS + ".gz", gzip.compress(numbers, mtime=0))
        return {"identifier": ident, "kind": "hocr" if index is not None else "searchtext_only", "files": files}
    meta_raw = get(METADATA.format(ident=ident), refusals=refusals)
    meta = json.loads(meta_raw.decode("utf-8"))
    files = {"metadata": (ident + "_meta.json.gz", gzip.compress(meta_raw, mtime=0))}
    names = [f["name"] for f in meta.get("files") or []]
    search = next((f for f in names if f.endswith(SEARCHTEXT)), None)
    if search:
        text = _try(get, ident, search, refusals)
        if text is not None:
            files["searchtext"] = (search, text)
            index_name = search[: -len(SEARCHTEXT)] + PAGEINDEX
            index = _try(get, ident, index_name, refusals) if index_name in names else None
            if index is not None:
                files["pageindex"] = (index_name, index)
                numbers_name = search[: -len(SEARCHTEXT)] + PAGE_NUMBERS
                numbers = _try(get, ident, numbers_name, refusals) if numbers_name in names else None
                if numbers is not None:
                    files["page_numbers"] = (numbers_name + ".gz", gzip.compress(numbers, mtime=0))
            return {"identifier": ident, "kind": "hocr" if index is not None else "searchtext_only", "files": files}
    djvu = next((f for f in names if f.endswith(DJVU)), None)
    data = _try(get, ident, djvu, refusals) if djvu else None
    if data is None:
        return {"identifier": ident, "kind": "no_text", "files": files}
    files["djvu_txt"] = (djvu + ".gz", gzip.compress(data, mtime=0))
    return {"identifier": ident, "kind": "djvu_txt", "files": files}


STATE_PREFIX = f"{R2_PREFIX}/_state/manifest"
SYNC_EVERY = 500


def _complete_lines(manifest: Path) -> list:
    if not manifest.exists():
        return []
    raw = manifest.read_bytes()
    end = raw.rfind(b"\n") + 1          # a line cut short by a stop is not synced
    return raw[:end].decode("utf-8").splitlines(keepends=True)


def sync_manifest(store, out: Path, *, final: bool = False, every: Optional[int] = None) -> int:
    """Copy manifest lines not yet on R2 there, as numbered chunks (_state/manifest/<first line>.jsonl).
    A chunk is written only when it holds SYNC_EVERY lines, or at the end of a run, so the chunks
    never overlap. Returns how many lines R2 now holds."""
    every = every or SYNC_EVERY
    synced_path = out / "manifest.synced"
    synced = int(synced_path.read_text(encoding="ascii")) if synced_path.exists() else 0
    lines = _complete_lines(out / "manifest.jsonl")
    while len(lines) - synced >= every or (final and len(lines) > synced):
        chunk = lines[synced: synced + every]
        store.put(f"{STATE_PREFIX}/{synced:08d}.jsonl", "".join(chunk).encode("utf-8"))
        synced += len(chunk)
        synced_path.write_text(str(synced), encoding="ascii")
    return synced


def restore_manifest(store, out: Path) -> int:
    """On a machine with no local manifest, rebuild it from the chunks on R2, so the fetch resumes
    without fetching again any item R2 already holds. Returns the number of lines restored."""
    manifest = out / "manifest.jsonl"
    if manifest.exists() and manifest.stat().st_size:
        return 0
    keys = sorted(store.list(STATE_PREFIX + "/"))
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    with manifest.open("wb") as fh:
        for key in keys:
            data = store.get(key)
            fh.write(data)
            total += data.count(b"\n")
    (out / "manifest.synced").write_text(str(total), encoding="ascii")
    return total


def write_status(out: Path, total: int, counts: dict, limit_state: dict) -> dict:
    """status.json: items recorded, the rate over the last hour and the last day, and a projected
    finish at the last day's rate."""
    from datetime import timedelta
    times = []
    done = set()
    for line in _complete_lines(out / "manifest.jsonl"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") != "error":
            done.add(row["identifier"])
            times.append(row["at"])
    stamp = datetime.now(timezone.utc)
    parsed = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times]
    hour = sum(1 for t in parsed if (stamp - t).total_seconds() <= 3600)
    day = sum(1 for t in parsed if (stamp - t).total_seconds() <= 86400)
    span_h = min(24.0, max(1.0, (stamp - min(parsed)).total_seconds() / 3600)) if parsed else 1.0
    per_hour = day / span_h if day else 0.0
    remaining = max(0, total - len(done))
    status = {"at": now(), "done": len(done), "total": total, "remaining": remaining,
              "per_hour_last_hour": hour, "per_hour_last_day": round(per_hour, 1),
              "projected_finish": (stamp + timedelta(hours=remaining / per_hour)).strftime("%Y-%m-%d")
              if per_hour else None, "concurrency": limit_state, "this_run": dict(counts)}
    (out / "status.json").write_text(json.dumps(status, indent=1, sort_keys=True), encoding="utf-8")
    return status


STATUS_KEY = f"{R2_PREFIX}/_state/status.json"
ORDER_KEY = f"{R2_PREFIX}/_state/order.txt"


RETRY_WINDOW = 500      # items between retries of the ones that failed
MAX_ATTEMPTS = 3        # tries per item in one run; after that it waits for the next pass


def run(identifiers: list, out: Path, *, store=None, get: Callable = None, workers: Optional[int] = None,
        log: Callable[[str], None] = print, stop_after: Optional[int] = None, keep_local: bool = True,
        deadline: Optional[float] = None, sync_every: Optional[int] = None, runner: Optional[str] = None) -> dict:
    """Fetch every identifier not yet recorded. keep_local=False streams each item's files to R2 only
    (the cloud runners: nothing but the manifest is written to disk). deadline (time.monotonic) ends
    the run cleanly: no new item starts after it, uploads finish and the manifest is synced."""
    import time as _time
    get = get or net.get
    workers = workers or net.LIMIT.ceiling
    refusals = net.RefusalCounter()
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    if store is not None:
        restored = restore_manifest(store, out)
        if restored:
            log(f"restored {restored} manifest lines from R2")
    done = done_identifiers(manifest)
    todo = [i for i in identifiers if i not in done]
    if stop_after is not None:
        todo = todo[:stop_after]
    lock = threading.Lock()
    uploads = ThreadPoolExecutor(max_workers=4) if store is not None else None
    counts = {"fetched": 0, "no_text": 0, "errors": 0, "already": len(done), "todo": len(todo)}
    stop = threading.Event()
    failed = []

    out_of_time = threading.Event()

    def one(ident: str) -> None:
        if stop.is_set() or out_of_time.is_set():
            return
        if deadline is not None and _time.monotonic() >= deadline:
            out_of_time.set()
            return
        try:
            item = fetch_item(ident, get, refusals)
        except net.TooManyRefusals as exc:
            stop.set()
            log(f"STOPPED: {exc}")
            return
        except Exception as exc:     # an item that keeps failing is recorded and the fetch goes on
            with lock:
                counts["errors"] += 1
                failed.append(ident)
                with manifest.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"identifier": ident, "kind": "error", "error": str(exc)[:200], "at": now()}) + "\n")
            return
        record = {"identifier": ident, "kind": item["kind"], "files": {}, "at": now()}
        folder = out / ident[:2] / ident
        for role, (name, data) in item["files"].items():
            if keep_local or store is None:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(data)
            entry = {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if store is not None:
                entry["r2_key"] = f"{R2_PREFIX}/{ident}/{name}"
            record["files"][role] = entry
        if uploads is not None:
            # The manifest line is written once R2 holds every file, so a stop never records an
            # item whose upload did not finish.
            uploads.submit(upload_then_record, record, folder, item["files"])
        else:
            write_record(record)

    def write_record(record: dict) -> None:
        with lock:
            counts["no_text" if record["kind"] == "no_text" else "fetched"] += 1
            with manifest.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
            n = counts["fetched"] + counts["no_text"] + counts["errors"]
            if n % 200 == 0:
                log(f"{n} of {len(todo)} this run ({counts}; {net.LIMIT.state()})")
            if n % 50 == 0:
                status = write_status(out, len(identifiers), counts, net.LIMIT.state())
                if store is not None:
                    try:
                        sync_manifest(store, out, every=sync_every)
                        store.put(STATUS_KEY, json.dumps({**status, "runner": runner}, sort_keys=True).encode("utf-8"))
                    except Exception as exc:       # retried at the next sync; never stops the fetch
                        log(f"manifest sync to R2 failed: {str(exc)[:200]}")

    def upload_then_record(record: dict, folder: Path, files: dict) -> None:
        try:
            for role, (name, data) in files.items():
                store.put(record["files"][role]["r2_key"], data)
        except Exception as exc:
            with lock:
                counts["errors"] += 1
                failed.append(record["identifier"])
            log(f"upload of {record['identifier']} failed: {str(exc)[:200]}")
            return
        write_record(record)

    # The pool has a thread for the highest concurrency allowed; net.LIMIT decides how many
    # requests actually run at once. The list is worked in windows of RETRY_WINDOW items: an item that
    # failed in one window (a 500, a 503 after the retries, a DNS failure, an upload) is tried again
    # at the start of the next, up to MAX_ATTEMPTS times in a run, so a shard is not left an item
    # short until the next pass.
    attempts = {}
    queue = list(todo)
    with ThreadPoolExecutor(max_workers=min(workers, net.LIMIT.ceiling)) as pool:
        while queue and not stop.is_set() and not out_of_time.is_set():
            window, queue = queue[:RETRY_WINDOW], queue[RETRY_WINDOW:]
            for ident in window:
                attempts[ident] = attempts.get(ident, 0) + 1
            list(pool.map(one, window))
            if uploads is not None:
                # This window's uploads finish first, so their failures are known before the next.
                uploads.shutdown(wait=True)
                uploads = ThreadPoolExecutor(max_workers=4)
            with lock:
                again = [i for i in dict.fromkeys(failed) if attempts.get(i, 0) < MAX_ATTEMPTS]
                failed.clear()
            if again and not out_of_time.is_set():
                counts["retried"] = counts.get("retried", 0) + len(again)
                queue = again + queue
    if uploads is not None:
        uploads.shutdown(wait=True)
        sync_manifest(store, out, final=True, every=sync_every)
    counts["stopped"] = stop.is_set()
    counts["out_of_time"] = out_of_time.is_set()
    status = write_status(out, len(identifiers), counts, net.LIMIT.state())
    if store is not None:
        store.put(STATUS_KEY, json.dumps({**status, "runner": runner}, sort_keys=True).encode("utf-8"))
    return counts
