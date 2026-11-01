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
stops with a report when 429 or 503 responses pile up."""
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
                out.add(json.loads(line)["identifier"])
            except (ValueError, KeyError):
                continue          # a line cut short by a stop: the item is fetched again
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


def run(identifiers: list, out: Path, *, store=None, get: Callable = None, workers: int = 2,
        log: Callable[[str], None] = print, stop_after: Optional[int] = None) -> dict:
    get = get or net.get
    refusals = net.RefusalCounter()
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    done = done_identifiers(manifest)
    todo = [i for i in identifiers if i not in done]
    if stop_after is not None:
        todo = todo[:stop_after]
    lock = threading.Lock()
    uploads = ThreadPoolExecutor(max_workers=4) if store is not None else None
    counts = {"fetched": 0, "no_text": 0, "errors": 0, "already": len(done), "todo": len(todo)}
    stop = threading.Event()

    def one(ident: str) -> None:
        if stop.is_set():
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
                with manifest.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"identifier": ident, "kind": "error", "error": str(exc)[:200], "at": now()}) + "\n")
            return
        record = {"identifier": ident, "kind": item["kind"], "files": {}, "at": now()}
        folder = out / ident[:2] / ident
        for role, (name, data) in item["files"].items():
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
                log(f"{n} of {len(todo)} this run ({counts})")

    def upload_then_record(record: dict, folder: Path, files: dict) -> None:
        try:
            for role, (name, data) in files.items():
                store.put(record["files"][role]["r2_key"], data)
        except Exception as exc:
            with lock:
                counts["errors"] += 1
            log(f"upload of {record['identifier']} failed: {str(exc)[:200]}")
            return
        write_record(record)

    with ThreadPoolExecutor(max_workers=min(workers, net.MAX_CONCURRENCY)) as pool:
        list(pool.map(one, todo))
    if uploads is not None:
        uploads.shutdown(wait=True)
    counts["stopped"] = stop.is_set()
    return counts
