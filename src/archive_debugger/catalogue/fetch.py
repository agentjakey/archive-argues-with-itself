"""Fetch the catalogue record of every item in the collection with the scrape API.

The scrape API pages through a query with a cursor, 10,000 records a page. Every page is kept as
fetched (gzip, with its sha256 in pages.json) under the cache folder, so a stopped fetch resumes at
the page after the last one cached and a finished one is never fetched again. The records are then
written once to catalogue.jsonl.gz, one per line, exactly as the API gave them."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from archive_debugger.catalogue import net

SCRAPE = "https://archive.org/services/search/v1/scrape"
FIELDS = ("identifier,title,date,year,publisher,creator,language,collection,subject,imagecount,mediatype,"
          "licenseurl,rights,publicdate,addeddate,volume,description")
PAGE_SIZE = 10000


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_catalogue(query: str, cache: Path, *, get: Callable = None, log: Callable[[str], None] = print,
                    max_pages: int = 100) -> dict:
    get = get or net.get
    refusals = net.RefusalCounter()
    cache.mkdir(parents=True, exist_ok=True)
    index_path = cache / "pages.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else \
        {"query": query, "fields": FIELDS, "pages": [], "started_at": now(), "complete": False}
    if index["query"] != query or index["fields"] != FIELDS:
        raise ValueError(f"{cache} holds a different query or field list: use another folder")
    while not index["complete"] and len(index["pages"]) < max_pages:
        cursor = index["pages"][-1]["next_cursor"] if index["pages"] else None
        params = {"q": query, "fields": FIELDS, "count": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        raw = get(SCRAPE, params, refusals=refusals) if get is net.get else get(SCRAPE, params)
        body = json.loads(raw.decode("utf-8"))
        if "error" in body:
            raise RuntimeError(f"scrape API error: {str(body['error'])[:300]}")
        n = len(index["pages"])
        name = f"page-{n:04d}.json.gz"
        packed = gzip.compress(raw, mtime=0)
        (cache / name).write_bytes(packed)
        entry = {"file": name, "sha256": hashlib.sha256(packed).hexdigest(), "items": len(body.get("items") or []),
                 "total": body.get("total"), "next_cursor": body.get("cursor"), "fetched_at": now()}
        index["pages"].append(entry)
        index["complete"] = not body.get("cursor")
        index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
        log(f"page {n}: {entry['items']} records (total {entry['total']})")
    if index["complete"]:
        index["finished_at"] = index.get("finished_at") or now()
        index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def records(cache: Path):
    """Every record of a cached fetch, each page checked against its sha256 first."""
    index = json.loads((cache / "pages.json").read_text(encoding="utf-8"))
    for entry in index["pages"]:
        packed = (cache / entry["file"]).read_bytes()
        if hashlib.sha256(packed).hexdigest() != entry["sha256"]:
            raise ValueError(f"{entry['file']} does not match its sha256")
        for item in json.loads(gzip.decompress(packed).decode("utf-8")).get("items") or []:
            yield item


def write_catalogue(cache: Path, out: Path) -> dict:
    seen, rows = set(), 0
    with gzip.open(out, "wt", encoding="utf-8", newline="\n") as fh:
        for item in records(cache):
            if item["identifier"] in seen:
                continue
            seen.add(item["identifier"])
            fh.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")
            rows += 1
    return {"records": rows, "file": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
