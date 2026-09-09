"""Phase 2 harvest: build the public_health pilot corpus.

Three stages, all reproducible and resumable from the on-disk cache:

  1. manifest  - page advancedsearch.php over the clean Canadian-government clause
                 and write every matching item to manifest.jsonl. The scrape API
                 is not used: the corpus is well under the 10k deep-paging window
                 and the scrape endpoint throttles to a canned baseline.
  2. enrich    - per item, read the metadata API, pick ONE OCR derivative by
                 priority (hOCR > DjVu XML > DjVuTXT), record the OCR flags, page
                 map, page count, and year, and write items.jsonl. Items with no
                 OCR derivative are skipped and counted, never faked.
  3. download  - fetch the chosen derivative (and page_numbers.json / scandata if
                 present) into a content-addressed cache under raw/. A file is
                 never re-downloaded once cached.

All IA-corpus network code lives in this module. Nothing downstream may re-fetch
IA corpus data; everything after harvest runs from raw/ and civic.db.

Dates are never dropped or imputed: undated items are kept and marked so they can
be routed to an undated bucket downstream. The binning window in pilot.toml is a
downstream bucketing concern, not a harvest filter.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlencode

from archive_debugger.harvest import discover, explore
from archive_debugger.harvest.discover import ThrottleError

# Positional-OCR formats. Their presence is the has_word_coords capability; the
# parsed source is chosen separately (DjVuTXT preferred) by select_source.
WORD_COORD_FORMATS = ("hOCR", "Djvu XML")

log = logging.getLogger("harvest.fetch")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


@dataclass
class PilotConfig:
    topic: str
    query: str
    mediatype: str
    collections: list[str]
    fields: str
    manifest_rows: int
    request_delay: float
    cache_dir: Path
    contact: str
    usable_floor: int


def load_pilot(path: Path) -> PilotConfig:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    corpus = raw["corpus"]
    harvest = raw["harvest"]
    return PilotConfig(
        topic=corpus["topic"],
        query=corpus["query"],
        mediatype=corpus.get("mediatype", "texts"),
        collections=list(corpus["collections"]["clean"]),
        fields=harvest["fields"],
        manifest_rows=int(harvest.get("manifest_rows", 100)),
        request_delay=float(harvest.get("request_delay_seconds", 0.5)),
        cache_dir=Path(harvest.get("cache_dir", "raw")),
        contact=harvest.get("user_agent_contact", ""),
        usable_floor=int(raw["corpus"].get("limits", {}).get("usable_floor", 2500)),
    )


def collection_clause(collections: list[str]) -> str:
    return "collection:(" + " OR ".join(collections) + ")"


def corpus_query(cfg: PilotConfig) -> str:
    return (
        f"mediatype:{cfg.mediatype} AND {collection_clause(cfg.collections)} "
        f"AND ({cfg.query})"
    )


# --------------------------------------------------------------------------- #
# Stage 1: manifest via advancedsearch paging
# --------------------------------------------------------------------------- #


# advancedsearch.php pages with a 1-indexed `page` parameter and IGNORES Solr's
# `start`. A stable sort is required so pages do not overlap or skip items.
MANIFEST_SORT = "identifier asc"


def manifest_page_url(query: str, *, rows: int, page: int, fields: str, sort: str = MANIFEST_SORT) -> str:
    params = [("q", query), ("rows", str(rows)), ("page", str(page)), ("output", "json")]
    params += [("sort[]", sort)]
    params += [("fl[]", f) for f in fields.split(",")]
    return f"{discover.ADVANCEDSEARCH_URL}?{urlencode(params)}"


def harvest_manifest(cfg: PilotConfig, out_path: Path, *, ctx: dict) -> list[dict]:
    """Page the full corpus into manifest.jsonl. Returns the list of docs. A fully
    cached rerun makes zero network calls."""
    query = corpus_query(cfg)
    # Guard: confirm the search surface is honoring the query before trusting it.
    discover.assert_healthy(collection_clause(cfg.collections), ctx=ctx)

    docs: list[dict] = []
    seen: set = set()
    page = 1
    num_found = None
    while True:
        url = manifest_page_url(query, rows=cfg.manifest_rows, page=page, fields=cfg.fields)
        data = discover.cached_get_json(url, **ctx)
        response = data.get("response", {})
        if num_found is None:
            num_found = response.get("numFound", 0)
        page_docs = response.get("docs", [])
        if not page_docs:
            break
        # Guard against a paging regression (repeated page): stop if a whole page
        # adds nothing new.
        new_docs = [d for d in page_docs if d.get("identifier") not in seen]
        if not new_docs:
            break
        for d in new_docs:
            seen.add(d.get("identifier"))
        docs.extend(new_docs)
        page += 1
        if len(docs) >= num_found:
            break
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    log.info("manifest: %s items (numFound %s) -> %s", len(docs), num_found, out_path)
    return docs


# --------------------------------------------------------------------------- #
# Stage 2: enrich from the metadata API
# --------------------------------------------------------------------------- #


def _files(meta: dict) -> list[dict]:
    return meta.get("files", []) or []


def _find_by_format(meta: dict, fmt: str, name_suffix: str) -> Optional[dict]:
    for f in _files(meta):
        if f.get("format") == fmt or (f.get("name", "").endswith(name_suffix)):
            return f
    return None


def find_djvutxt(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "DjVuTXT", "_djvu.txt")


def find_djvuxml(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "Djvu XML", "_djvu.xml")


def find_hocr(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "hOCR", "_hocr.html")


def find_page_numbers(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "Page Numbers JSON", "_page_numbers.json")


def find_scandata(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "Scandata", "_scandata.xml")


def find_chocr(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "chOCR", "_chocr.html.gz")


def select_source(meta: dict) -> tuple[Optional[str], Optional[dict]]:
    """Choose the ONE OCR file to parse downstream. Prefer plain text (DjVuTXT);
    fall back to DjVu XML, then hOCR. Returns (ocr_format, file_entry) where
    ocr_format is the parser switch: 'DjVuTXT' | 'DjVuXML' | 'hOCR'."""
    txt = find_djvutxt(meta)
    if txt is not None:
        return "DjVuTXT", txt
    xml = find_djvuxml(meta)
    if xml is not None:
        return "DjVuXML", xml
    hocr = find_hocr(meta)
    if hocr is not None:
        return "hOCR", hocr
    return None, None


def word_coords_capable(meta: dict) -> bool:
    """Capability flag: does the item carry positional OCR (hOCR or DjVu XML)
    from which word-level coordinates COULD be derived later. Independent of which
    source is parsed."""
    formats = discover.file_formats(meta)
    return any(fmt in formats for fmt in WORD_COORD_FORMATS)


def page_count_of(meta: dict) -> Optional[int]:
    value = meta.get("metadata", {}).get("imagecount")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ocr_engine_of(meta: dict) -> Optional[str]:
    return meta.get("metadata", {}).get("ocr")


def _file_ref(entry: Optional[dict]) -> Optional[dict]:
    if entry is None:
        return None
    return {"name": entry.get("name"), "md5": entry.get("md5"), "size": entry.get("size")}


def build_record(doc: dict, meta: dict) -> Optional[dict]:
    """Build the per-item harvest record, or None if the item has no OCR and must
    be skipped."""
    ocr_format, src = select_source(meta)
    if src is None:
        return None
    year = explore.item_year(doc)
    if year is None:
        year = discover.meta_year(meta)
    page_numbers = find_page_numbers(meta)
    identifier = doc.get("identifier")
    md = meta.get("metadata", {})
    record = {
        "identifier": identifier,
        # Raw harvest fields, preserved verbatim. creator and publisher are kept
        # separate on purpose: issuer normalization happens in Phase 5.
        "title": explore._as_text(doc.get("title")),
        "creator_raw": doc.get("creator"),
        "publisher_raw": doc.get("publisher"),
        "date_raw": doc.get("date"),
        "collection_raw": doc.get("collection"),
        "language": doc.get("language"),
        "mediatype": doc.get("mediatype"),
        "details_url": f"https://archive.org/details/{identifier}",
        "license": md.get("licenseurl"),
        # Preliminary harvest date; Phase 5 is the source of truth, so downstream
        # loaders ignore these for the normalized columns.
        "year": year,
        "dated": year is not None,
        # OCR-derivative facts.
        "ocr_format": ocr_format,
        "ocr_engine": ocr_engine_of(meta),
        "has_word_coords": word_coords_capable(meta),
        "has_printed_page_map": page_numbers is not None,
        "page_count": page_count_of(meta),
        "ocr_file_ref": content_ref(src["md5"], src["name"]) if src.get("md5") and src.get("name") else None,
        "ocr_file": _file_ref(src),
        "page_numbers_file": _file_ref(page_numbers),
        "scandata_file": _file_ref(find_scandata(meta)),
    }
    return record


def _read_jsonl_ids(path: Path) -> set:
    ids: set = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["identifier"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def enrich(
    docs: Iterable[dict],
    out_path: Path,
    *,
    ctx: dict,
    limit: Optional[int] = None,
) -> tuple[list[dict], list[str]]:
    """Enrich manifest docs into per-item records, appending each result to
    items.jsonl as it is built so progress is durable across interruptions.

    Resumable: identifiers already present in items.jsonl or the skipped-ids
    sidecar are not re-processed. Returns (records, skipped_ids) read back from
    disk. `limit` caps how many NEW items are processed this call, so the harvest
    can be advanced in bounded chunks.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    skipped_path = out_path.with_name("skipped_no_ocr.txt")

    done = _read_jsonl_ids(out_path)
    skipped_ids: list[str] = []
    if skipped_path.exists():
        skipped_ids = [s for s in skipped_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    already = done | set(skipped_ids)

    processed = 0
    with out_path.open("a", encoding="utf-8") as out_fh, skipped_path.open("a", encoding="utf-8") as skip_fh:
        for doc in docs:
            if limit is not None and processed >= limit:
                break
            ident = doc.get("identifier")
            if ident in already:
                continue
            meta = discover.fetch_metadata(ident, ctx=ctx)
            record = build_record(doc, meta)
            if record is None:
                skip_fh.write(ident + "\n")
                skip_fh.flush()
                skipped_ids.append(ident)
                log.warning("no OCR derivative, skipping: %s", ident)
            else:
                out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_fh.flush()
                done.add(ident)
            already.add(ident)
            processed += 1

    records: list[dict] = []
    with out_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    log.info(
        "enrich: %s new this call; %s usable, %s skipped total -> %s",
        processed, len(records), len(skipped_ids), out_path,
    )
    return records, skipped_ids


# --------------------------------------------------------------------------- #
# Stage 3: content-addressed download of chosen derivatives
# --------------------------------------------------------------------------- #


def content_ref(md5: str, name: str) -> str:
    """Deterministic, cache-root-relative content address for a file. Phase 4
    joins this to raw/ to locate the cached derivative."""
    base = os.path.basename(name)
    return f"ocr/{md5[:2]}/{md5}__{base}"


def content_path(cache_dir: Path, md5: str, name: str) -> Path:
    return cache_dir / content_ref(md5, name)


DOWNLOAD_UA = (
    "archive-argues-with-itself/0.0 "
    "(+https://github.com/agentjakey/archive-argues-with-itself)"
)


def _default_downloader(identifier: str, filename: str, dest_path: str) -> None:
    """Stream one IA file straight to disk from the public download endpoint.
    Direct requests streaming (chunked) keeps memory flat and avoids the
    internetarchive get_item metadata round-trip per item. Lazily imports
    requests so the tests need no extra dependency."""
    import requests
    from urllib.parse import quote

    url = f"https://archive.org/download/{quote(identifier)}/{quote(filename)}"
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": DOWNLOAD_UA}) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)


def download_file(
    identifier: str,
    file_entry: dict,
    cache_dir: Path,
    *,
    downloader: Callable[[str, str, str], None] = _default_downloader,
    sleeper: Callable[[float], None] = time.sleep,
    delay: float = 0.5,
) -> tuple[Path, bool]:
    """Download a file to its content-addressed path. Returns (path, downloaded).
    A cached file is never re-downloaded."""
    md5 = file_entry["md5"]
    name = file_entry["name"]
    dest = content_path(cache_dir, md5, name)
    if dest.exists():
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    downloader(identifier, name, str(tmp))
    tmp.replace(dest)
    sleeper(delay)
    return dest, True


DOWNLOAD_KEYS = ("ocr_file", "page_numbers_file", "scandata_file")


def load_records(items_path: Path) -> list[dict]:
    records: list[dict] = []
    with items_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _iter_item_files(record: dict, keys: tuple = DOWNLOAD_KEYS):
    for key in keys:
        entry = record.get(key)
        if entry and entry.get("md5") and entry.get("name"):
            yield entry


def _write_checkpoint(path: Optional[Path], data: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def download_corpus(
    records: list[dict],
    cache_dir: Path,
    *,
    downloader: Callable[[str, str, str], None] = _default_downloader,
    sleeper: Callable[[float], None] = time.sleep,
    delay: float = 0.5,
    new_limit: Optional[int] = None,
    batch: int = 100,
    checkpoint_path: Optional[Path] = None,
    keys: tuple = DOWNLOAD_KEYS,
) -> dict:
    """Download the given file keys per item into the content-addressed cache.
    Streams to disk (never holds a file in memory); skip-cached; fault-tolerant
    (a per-file error is recorded, not fatal). Writes a checkpoint every `batch`
    new downloads so a kill loses at most one batch. `new_limit` caps NEW
    downloads this call for bounded, resumable runs."""
    downloaded = cached = failed = 0
    failures: list[dict] = []
    for record in records:
        ident = record["identifier"]
        for entry in _iter_item_files(record, keys):
            dest = content_path(cache_dir, entry["md5"], entry["name"])
            if dest.exists():
                cached += 1
                continue
            try:
                download_file(ident, entry, cache_dir, downloader=downloader, sleeper=sleeper, delay=delay)
                downloaded += 1
            except Exception as exc:  # noqa: BLE001 - one bad file must not abort the run
                failed += 1
                failures.append({"identifier": ident, "file": entry["name"], "error": str(exc)[:200]})
                log.warning("download failed %s/%s: %s", ident, entry["name"], exc)
                continue
            if downloaded % batch == 0:
                _write_checkpoint(checkpoint_path, {"downloaded": downloaded, "cached": cached, "failed": failed, "last_identifier": ident})
            if new_limit is not None and downloaded >= new_limit:
                _write_checkpoint(checkpoint_path, {"downloaded": downloaded, "cached": cached, "failed": failed, "last_identifier": ident, "complete": False})
                return {"downloaded": downloaded, "already_cached": cached, "failed": failed, "failures": failures, "complete": False}
    _write_checkpoint(checkpoint_path, {"downloaded": downloaded, "cached": cached, "failed": failed, "complete": True})
    return {"downloaded": downloaded, "already_cached": cached, "failed": failed, "failures": failures, "complete": True}


# --------------------------------------------------------------------------- #
# Segmentation-source assignment (waterfall: valid-ff djvu.txt -> djvu.xml -> hOCR)
# --------------------------------------------------------------------------- #

FF_TOLERANCE = 2  # allow small blank-leaf differences between \f pages and leaf count


def _cached_djvutxt_ff(record: dict, cache_dir: Path) -> Optional[int]:
    """If this item's djvu.txt is cached, return its \\f-page count (ff+1), else
    None. Only meaningful while ocr_file still points at the djvu.txt."""
    entry = record.get("ocr_file")
    if not entry or not entry.get("md5") or not entry.get("name"):
        return None
    if not entry["name"].endswith("_djvu.txt"):
        return None
    path = content_path(cache_dir, entry["md5"], entry["name"])
    if not path.exists():
        return None
    ff = path.read_bytes().count(b"\x0c")
    return ff + 1


def _leaf_count(record: dict, cache_dir: Path, meta: dict) -> Optional[int]:
    """Authoritative leaf count from a cached page_numbers.json, else metadata
    imagecount, else None."""
    pn = record.get("page_numbers_file")
    if pn and pn.get("md5") and pn.get("name"):
        path = content_path(cache_dir, pn["md5"], pn["name"])
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return len(data.get("pages", []))
            except (json.JSONDecodeError, OSError):
                pass
    return page_count_of(meta)


def assign_segmentation(records: list[dict], cache_dir: Path, *, ctx: dict) -> tuple[list[dict], dict]:
    """Assign a segmentation_source per item by waterfall and rewrite ocr_format /
    ocr_file / ocr_file_ref to the chosen source. Requires the item's djvu.txt to
    be cached to be eligible for the djvu.txt branch (\\f detection needs bytes).
    Returns (updated_records, counts)."""
    counts = Counter()
    updated: list[dict] = []
    for record in records:
        meta = discover.fetch_metadata(record["identifier"], ctx=ctx)
        ff_pages = _cached_djvutxt_ff(record, cache_dir)
        leaves = _leaf_count(record, cache_dir, meta)
        xml = find_djvuxml(meta)
        hocr = find_hocr(meta)

        rec = dict(record)
        if ff_pages is not None and ff_pages > 1 and (
            leaves is None or abs(ff_pages - leaves) <= FF_TOLERANCE
        ):
            rec["segmentation_source"] = "djvutxt"
            rec["segmentation_reason"] = (
                f"djvu.txt has {ff_pages} form-feed pages"
                + ("" if leaves is None else f" ~ {leaves} leaves")
            )
            rec["ocr_format"] = "DjVuTXT"
            # ocr_file already points at djvu.txt
        elif xml is not None:
            rec["segmentation_source"] = "djvuxml"
            reason = "no valid form-feed" if ff_pages is not None else "djvu.txt not cached / no form-feed"
            rec["segmentation_reason"] = reason + " -> djvu.xml OBJECT-per-page"
            rec["ocr_format"] = "DjVuXML"
            rec["ocr_file"] = _file_ref(xml)
            rec["ocr_file_ref"] = content_ref(xml["md5"], xml["name"]) if xml.get("md5") and xml.get("name") else None
        elif hocr is not None:
            rec["segmentation_source"] = "hocr"
            rec["segmentation_reason"] = "no djvu.txt form-feed and no djvu.xml -> hOCR"
            rec["ocr_format"] = "hOCR"
            rec["ocr_file"] = _file_ref(hocr)
            rec["ocr_file_ref"] = content_ref(hocr["md5"], hocr["name"]) if hocr.get("md5") and hocr.get("name") else None
        else:
            rec["segmentation_source"] = None
            rec["segmentation_reason"] = "no usable structured derivative"
        counts[rec["segmentation_source"]] += 1
        updated.append(rec)
    return updated, dict(counts)


# --------------------------------------------------------------------------- #
# Integrity
# --------------------------------------------------------------------------- #


def _file_looks_empty(path: Path) -> bool:
    """True if the file is zero-byte or has no non-whitespace content in its head.
    Only a small head is read, so this stays memory-light."""
    try:
        if path.stat().st_size == 0:
            return True
        with path.open("rb") as fh:
            head = fh.read(8192)
        return len(head.strip()) == 0
    except OSError:
        return True


def integrity_check(records: list[dict], cache_dir: Path) -> dict:
    """Assert one cached source file per item. Reports present/missing/empty, the
    total bytes of source files, and counts by ocr_format."""
    present = 0
    total_bytes = 0
    missing: list[dict] = []
    empty: list[dict] = []
    by_format: Counter = Counter()
    for record in records:
        by_format[record.get("ocr_format")] += 1
        entry = record.get("ocr_file")
        ident = record.get("identifier")
        if not entry or not entry.get("md5") or not entry.get("name"):
            missing.append({"identifier": ident, "reason": "no source file ref"})
            continue
        dest = content_path(cache_dir, entry["md5"], entry["name"])
        if not dest.exists():
            missing.append({"identifier": ident, "file": entry["name"], "reason": "missing"})
            continue
        if _file_looks_empty(dest):
            empty.append({"identifier": ident, "file": entry["name"]})
            continue
        present += 1
        total_bytes += dest.stat().st_size
    return {
        "manifest_count": len(records),
        "source_present": present,
        "total_source_bytes": total_bytes,
        "by_ocr_format": dict(by_format),
        "missing": missing,
        "empty": empty,
    }


def run_integrity(
    records: list[dict],
    cache_dir: Path,
    *,
    downloader: Callable[[str, str, str], None] = _default_downloader,
    sleeper: Callable[[float], None] = time.sleep,
    delay: float = 0.5,
) -> dict:
    """Integrity check, then re-fetch any missing or empty source file once, then
    re-check. Returns the final report plus the list still failing after retry."""
    report = integrity_check(records, cache_dir)
    by_id = {r.get("identifier"): r for r in records}
    to_refetch = report["missing"] + report["empty"]
    still_failing: list[dict] = []
    for bad in to_refetch:
        record = by_id.get(bad["identifier"])
        entry = record.get("ocr_file") if record else None
        if not entry or not entry.get("md5"):
            still_failing.append({**bad, "retry": "no ref"})
            continue
        dest = content_path(cache_dir, entry["md5"], entry["name"])
        if dest.exists() and _file_looks_empty(dest):
            dest.unlink(missing_ok=True)  # force a clean re-download
        try:
            download_file(bad["identifier"], entry, cache_dir, downloader=downloader, sleeper=sleeper, delay=delay)
        except Exception as exc:  # noqa: BLE001
            still_failing.append({"identifier": bad["identifier"], "file": entry["name"], "error": str(exc)[:200]})
    final = integrity_check(records, cache_dir)
    final["still_failing_after_retry"] = still_failing
    return final


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def summarize(records: list[dict], skipped: list[str], manifest_count: int, floor: int) -> dict:
    usable = len(records)
    fmt_counts = Counter(r["ocr_format"] for r in records)
    word_coords = sum(1 for r in records if r["has_word_coords"])
    page_map = sum(1 for r in records if r["has_printed_page_map"])
    undated = sum(1 for r in records if not r["dated"])
    decade_counts: Counter = Counter()
    for r in records:
        decade_counts[explore.decade_label(r["year"])] += 1
    return {
        "manifest_count": manifest_count,
        "usable_count": usable,
        "skipped_no_ocr": len(skipped),
        "usable_floor": floor,
        "clears_floor": usable >= floor,
        "ocr_format_breakdown": dict(fmt_counts.most_common()),
        "has_word_coords": word_coords,
        "has_word_coords_pct": explore._pct(word_coords, usable),
        "has_printed_page_map": page_map,
        "has_printed_page_map_pct": explore._pct(page_map, usable),
        "undated": undated,
        "undated_pct": explore._pct(undated, usable),
        "decade_distribution": dict(sorted(decade_counts.items())),
    }


def write_summary(out_dir: Path, summary: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "harvest_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    lines = [
        "# Harvest summary (public_health)",
        "",
        f"Manifest items: {summary['manifest_count']}",
        f"Usable (has OCR): {summary['usable_count']}  |  floor {summary['usable_floor']}  "
        f"|  clears floor: {'yes' if summary['clears_floor'] else 'NO'}",
        f"Skipped (no OCR derivative): {summary['skipped_no_ocr']}",
        "",
        "## OCR format breakdown",
        "",
        "| format | count |",
        "| --- | ---: |",
    ]
    for fmt, n in summary["ocr_format_breakdown"].items():
        lines.append(f"| {fmt} | {n} |")
    lines += [
        "",
        f"has_word_coords (hOCR/DjVu XML): {summary['has_word_coords']} "
        f"({summary['has_word_coords_pct']}%) - bounds later bbox-level precision.",
        f"has_printed_page_map (page_numbers.json): {summary['has_printed_page_map']} "
        f"({summary['has_printed_page_map_pct']}%)",
        f"undated: {summary['undated']} ({summary['undated_pct']}%)",
        "",
        "## Decade distribution (usable items)",
        "",
        "| decade | count |",
        "| --- | ---: |",
    ]
    for dec, n in summary["decade_distribution"].items():
        lines.append(f"| {dec} | {n} |")
    lines.append("")
    (out_dir / "harvest_summary.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Orchestration / CLI
# --------------------------------------------------------------------------- #


def _make_ctx(cfg: PilotConfig, cache_dir: Path, *, offline: bool) -> dict:
    return {
        "cache_dir": cache_dir,
        "transport": discover.default_transport,
        "sleeper": time.sleep,
        "rng": random.Random(0),
        "headers": {"User-Agent": explore.user_agent(cfg.contact), "Accept": "application/json"},
        "page_delay": cfg.request_delay,
        "offline": offline,
    }


def run(
    config_path: Path,
    out_dir: Path,
    *,
    contact: str,
    do_download: bool = False,
    download_sample: Optional[int] = None,
    enrich_limit: Optional[int] = None,
    offline: bool = False,
) -> dict:
    cfg = load_pilot(config_path)
    if contact:
        cfg.contact = contact
    search_cache = cfg.cache_dir / "search_cache"
    ctx = _make_ctx(cfg, search_cache, offline=offline)

    manifest_path = out_dir / "manifest.jsonl"
    items_path = out_dir / "items.jsonl"

    docs = harvest_manifest(cfg, manifest_path, ctx=ctx)
    records, skipped = enrich(docs, items_path, ctx=ctx, limit=enrich_limit)
    summary = summarize(records, skipped, len(docs), cfg.usable_floor)
    write_summary(out_dir, summary)

    if do_download or download_sample:
        new_limit = None if do_download else download_sample
        dl = download_corpus(
            records, cfg.cache_dir, delay=cfg.request_delay, new_limit=new_limit,
            checkpoint_path=out_dir / "download_checkpoint.json",
        )
        summary["download"] = dl
        write_summary(out_dir, summary)
    return summary


def run_download_all(config_path: Path, out_dir: Path, *, contact: str, new_limit: Optional[int]) -> dict:
    """Standalone: download every source derivative for the already-enriched
    items.jsonl. Resumable via the content-addressed cache."""
    cfg = load_pilot(config_path)
    if contact:
        cfg.contact = contact
    records = load_records(out_dir / "items.jsonl")
    return download_corpus(
        records, cfg.cache_dir, delay=cfg.request_delay, new_limit=new_limit,
        checkpoint_path=out_dir / "download_checkpoint.json",
    )


def run_integrity_pass(config_path: Path, out_dir: Path, *, contact: str) -> dict:
    cfg = load_pilot(config_path)
    if contact:
        cfg.contact = contact
    records = load_records(out_dir / "items.jsonl")
    report = run_integrity(records, cfg.cache_dir, delay=cfg.request_delay)
    with (out_dir / "integrity_report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 2 harvest for the public_health pilot.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default="data/harvest", type=Path)
    p.add_argument("--contact", default="")
    p.add_argument("--download", action="store_true", help="download all chosen derivatives")
    p.add_argument("--download-sample", type=int, default=None, help="download only the first N")
    p.add_argument("--download-all", action="store_true", help="standalone: download all sources for items.jsonl")
    p.add_argument("--integrity", action="store_true", help="standalone: integrity pass + re-fetch")
    p.add_argument("--new-limit", type=int, default=None, help="cap NEW downloads this call (resumable batches)")
    p.add_argument("--enrich-limit", type=int, default=None, help="cap items enriched (debug)")
    p.add_argument("--offline", action="store_true", help="use cache only; fail on cache miss")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    contact = args.contact or load_pilot(args.config).contact
    needs_network = not args.offline and (
        args.download or args.download_sample or args.download_all or args.integrity or True
    )
    if needs_network and not contact:
        print(
            "Refusing to hit the network without a contact for the User-Agent. Pass "
            "--contact you@example.com, set harvest.user_agent_contact in the config, "
            "or use --offline.",
            file=sys.stderr,
        )
        return 2

    if args.download_all:
        dl = run_download_all(args.config, args.out, contact=args.contact, new_limit=args.new_limit)
        print(f"download-all: {dl['downloaded']} new, {dl['already_cached']} cached, {dl['failed']} failed, complete={dl['complete']}")
        return 0
    if args.integrity:
        rep = run_integrity_pass(args.config, args.out, contact=args.contact)
        print(
            f"integrity: {rep['source_present']}/{rep['manifest_count']} source files present, "
            f"{rep['total_source_bytes']/1e9:.3f} GB, by_format={rep['by_ocr_format']}, "
            f"still_failing={len(rep['still_failing_after_retry'])}"
        )
        return 0

    try:
        summary = run(
            args.config,
            args.out,
            contact=args.contact,
            do_download=args.download,
            download_sample=args.download_sample,
            enrich_limit=args.enrich_limit,
            offline=args.offline,
        )
    except ThrottleError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        return 3
    print(
        f"Harvest: {summary['usable_count']} usable / {summary['manifest_count']} manifest "
        f"(floor {summary['usable_floor']}, clears: {summary['clears_floor']})"
    )
    print(f"See {args.out / 'harvest_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
