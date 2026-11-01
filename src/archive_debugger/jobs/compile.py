"""The compile job: fetched OCR text into the corpus's pages and passages, as a job (Phase 4, Part 3).

Input unit: <input_prefix>/units/<id>.json, {"items": [identifier, ...]}. For each item the job reads
the full-text fetch's files from the store (fulltext/v1/<identifier>/: the hOCR search text, its page
index and page_numbers.json) and the item's catalogue record, and writes <id>.jsonl.gz holding one
"item" line per document (its catalogue fields) followed by its "page" and "passage" lines, in the
corpus's own format: page ids "<identifier>#<leaf>" and passage ids "<identifier>#<leaf>:<n>", where
the leaf is the page's position among the leaves the archive.org viewer shows (its /page/n<leaf>),
taken from page_numbers.json. Passages are cut by the corpus builder's own chunker
(archive_debugger.ingest.ocr.build_passages), never across a page.

An item without page_numbers.json, or whose page index and page numbers disagree, gets no pages: it
is reported in the unit's "skipped" lines with the reason, so nothing is ever linked to the wrong
page. Packing units into an engine shard's corpus database is pack_shard below."""
from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Callable

from archive_debugger.ingest import ocr as ingest_ocr
from archive_debugger.jobs.spec import JobSpec

FULLTEXT_PREFIX = "fulltext/v1"


def shown_leaves(page_numbers: dict) -> dict:
    """{scanned leaf number: viewer leaf index} for the leaves the viewer shows, in order."""
    return {int(p["leafNum"]): i for i, p in enumerate(page_numbers.get("pages") or [])}


def item_pages(identifier: str, searchtext: str, pageindex: list, page_numbers: dict) -> tuple:
    """(pages, reason). Pages are corpus page dicts with their text; reason names why there are none."""
    mapping = shown_leaves(page_numbers)
    if not mapping:
        return [], "no page_numbers: link numbers unknown"
    printed = {i: (p.get("pageNumber") or None) for i, p in enumerate(page_numbers.get("pages") or [])}
    pages = []
    for scanned, entry in enumerate(pageindex):
        start, end = int(entry[0]), int(entry[1])
        if scanned not in mapping:
            continue                       # a scan the viewer does not show (a colour card, a blank)
        leaf = mapping[scanned]
        text = searchtext[start:end]
        pages.append({"page_id": f"{identifier}#{leaf}", "item_id": identifier, "leaf_index": leaf,
                      "printed_page": printed.get(leaf), "char_count": len(text), "ocr_conf_mean": None,
                      "has_text": 1 if text.strip() else 0, "_text": text})
    if len(pages) != len(mapping):
        return [], f"page index covers {len(pages)} of {len(mapping)} shown leaves"
    return pages, None


def compile_item(identifier: str, files: dict, record: dict, *, target_tokens: int, overlap_tokens: int) -> list:
    searchtext = gzip.decompress(files["searchtext"]).decode("utf-8", errors="replace")
    pageindex = json.loads(gzip.decompress(files["pageindex"]))
    page_numbers = json.loads(gzip.decompress(files["page_numbers"])) if files.get("page_numbers") else {}
    pages, reason = item_pages(identifier, searchtext, pageindex, page_numbers)
    lines = [{"kind": "item", "identifier": identifier, "record": record}]
    if reason:
        return lines + [{"kind": "skipped", "identifier": identifier, "reason": reason}]
    for page in pages:
        lines.append({"kind": "page", **{k: v for k, v in page.items() if k != "_text"}})
        for p in ingest_ocr.build_passages(identifier, page, target_tokens=target_tokens, overlap_tokens=overlap_tokens):
            lines.append({"kind": "passage", **p})
    return lines


def prepare(spec: JobSpec, store, args) -> list:
    """Units of items whose full text was fetched, from the fetch manifest (local) and the registry's
    choice of items (args.source: a file of identifiers, one per line)."""
    idents = [l.strip() for l in Path(args.source).read_text(encoding="utf-8").splitlines() if l.strip()]
    size = args.shard
    units = []
    for n in range(0, len(idents), size):
        uid = f"items-{n // size:05d}"
        store.put(f"{spec.input_prefix}/units/{uid}.json", json.dumps({"items": idents[n:n + size]}).encode("utf-8"))
        units.append({"id": uid, "items": len(idents[n:n + size])})
    return units


def make_process(spec: JobSpec, executor: str, *, records: Callable[[str], dict] = None) -> Callable:
    target = int(spec.params.get("target_tokens", 300))
    overlap = int(spec.params.get("overlap_tokens", 40))
    catalogue_key = spec.params.get("catalogue_key", "catalogue/v1/catalogue.jsonl.gz")
    cache: dict = {}

    def record_for(store, identifier: str) -> dict:
        if records is not None:
            return records(identifier)
        if "records" not in cache:
            raw = gzip.decompress(store.get(catalogue_key)).decode("utf-8")
            cache["records"] = {json.loads(l)["identifier"]: json.loads(l) for l in raw.splitlines() if l.strip()}
        return cache["records"].get(identifier, {})

    def process(unit: dict, store, _spec: JobSpec) -> tuple:
        idents = json.loads(store.get(f"{spec.input_prefix}/units/{unit['id']}.json"))["items"]
        out = []
        for ident in idents:
            prefix = f"{FULLTEXT_PREFIX}/{ident}/"
            names = {k.rsplit("/", 1)[-1]: k for k in store.list(prefix)}
            find = lambda suffix: next((names[n] for n in names if n.endswith(suffix)), None)  # noqa: E731
            keys = {"searchtext": find("_hocr_searchtext.txt.gz"), "pageindex": find("_hocr_pageindex.json.gz"),
                    "page_numbers": find("_page_numbers.json.gz")}
            if not keys["searchtext"] or not keys["pageindex"]:
                out.append({"kind": "skipped", "identifier": ident, "reason": "no page-indexed text fetched"})
                continue
            files = {role: store.get(key) for role, key in keys.items() if key}
            out += compile_item(ident, files, record_for(store, ident), target_tokens=target, overlap_tokens=overlap)
        body = gzip.compress("".join(json.dumps(l, ensure_ascii=True) + "\n" for l in out).encode("utf-8"), mtime=0)
        return body, "jsonl.gz", {"model": "ingest.ocr.build_passages", "backend": executor,
                                  "items": len(idents), "passages": sum(1 for l in out if l["kind"] == "passage"),
                                  "skipped": sum(1 for l in out if l["kind"] == "skipped")}
    return process


def pack_shard(unit_files: list, db_path: Path, *, init_db: Callable, normalize: Callable = None) -> dict:
    """Write compiled units into a corpus database (the engine's schema), then let the caller's
    normalize step fill issuer, jurisdiction and dates from the items' catalogue fields."""
    conn: sqlite3.Connection = init_db(db_path)
    counts = {"items": 0, "pages": 0, "passages": 0, "skipped": 0}
    from archive_debugger.ingest.build import _write_item
    for raw in unit_files:
        items, pages, passages = {}, {}, {}
        for line in gzip.decompress(raw).decode("utf-8").splitlines():
            row = json.loads(line)
            if row["kind"] == "item":
                items[row["identifier"]] = row["record"]
            elif row["kind"] == "page":
                pages.setdefault(row["item_id"], []).append(row)
            elif row["kind"] == "passage":
                passages.setdefault(row["item_id"], []).append(row)
            elif row["kind"] == "skipped":
                counts["skipped"] += 1
        for ident, rec in items.items():
            if ident not in pages:
                continue
            conn.execute("INSERT OR REPLACE INTO items (item_id, title, creator_raw, publisher_raw, date_raw, collection_raw, "
                         "language, mediatype, ocr_format, page_count, details_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (ident, _s(rec.get("title")), _s(rec.get("creator")), _s(rec.get("publisher")), _s(rec.get("date")),
                          json.dumps(rec.get("collection") if isinstance(rec.get("collection"), list) else [rec.get("collection")]),
                          _s(rec.get("language")), "texts", "hOCR", len(pages[ident]), f"https://archive.org/details/{ident}"))
            _write_item(conn, ident, pages[ident], passages.get(ident, []))
            counts["items"] += 1
            counts["pages"] += len(pages[ident])
            counts["passages"] += len(passages.get(ident, []))
    conn.commit()
    if normalize is not None:
        normalize(conn)
    return counts


def _s(value):
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v is not None)
    return value
