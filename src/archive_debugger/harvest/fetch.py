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

# OCR derivative selection priority. Word-level coordinates exist for the first
# two (positional OCR); DjVuTXT is plain text only.
OCR_PRIORITY = ("hOCR", "Djvu XML", "DjVuTXT")
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


def select_ocr(meta: dict) -> Optional[dict]:
    """Pick ONE OCR derivative file by priority. Returns the file entry annotated
    with its normalized ocr_format, or None if the item has no OCR derivative."""
    files = _files(meta)
    by_format: dict[str, dict] = {}
    for f in files:
        fmt = f.get("format")
        if fmt in OCR_PRIORITY and fmt not in by_format:
            by_format[fmt] = f
    for fmt in OCR_PRIORITY:
        if fmt in by_format:
            entry = dict(by_format[fmt])
            entry["ocr_format"] = fmt
            return entry
    return None


def _find_by_format(meta: dict, fmt: str, name_suffix: str) -> Optional[dict]:
    for f in _files(meta):
        if f.get("format") == fmt or (f.get("name", "").endswith(name_suffix)):
            return f
    return None


def find_page_numbers(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "Page Numbers JSON", "_page_numbers.json")


def find_scandata(meta: dict) -> Optional[dict]:
    return _find_by_format(meta, "Scandata", "_scandata.xml")


def has_word_coords(ocr_format: str) -> bool:
    return ocr_format in WORD_COORD_FORMATS


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
    ocr = select_ocr(meta)
    if ocr is None:
        return None
    ocr_format = ocr["ocr_format"]
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
        "has_word_coords": has_word_coords(ocr_format),
        "has_printed_page_map": page_numbers is not None,
        "page_count": page_count_of(meta),
        "ocr_file_ref": content_ref(ocr["md5"], ocr["name"]) if ocr.get("md5") and ocr.get("name") else None,
        "ocr_file": _file_ref(ocr),
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


def _default_downloader(identifier: str, filename: str, dest_path: str) -> None:
    """Download one file of an IA item via the internetarchive library. Imported
    lazily so the rest of the module (and the tests) need no extra dependency."""
    import internetarchive

    item = internetarchive.get_item(identifier)
    fileobj = item.get_file(filename)
    fileobj.download(file_path=dest_path, verbose=False)


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


def download_records(
    records: list[dict],
    cache_dir: Path,
    *,
    downloader: Callable[[str, str, str], None] = _default_downloader,
    sleeper: Callable[[float], None] = time.sleep,
    delay: float = 0.5,
    limit: Optional[int] = None,
) -> dict:
    """Download the chosen OCR derivative plus page_numbers/scandata for each
    record. Returns counts of downloaded vs already-cached files."""
    downloaded = cached = 0
    for i, record in enumerate(records):
        if limit is not None and i >= limit:
            break
        ident = record["identifier"]
        for key in ("ocr_file", "page_numbers_file", "scandata_file"):
            entry = record.get(key)
            if not entry or not entry.get("md5"):
                continue
            _, did = download_file(
                ident, entry, cache_dir, downloader=downloader, sleeper=sleeper, delay=delay
            )
            if did:
                downloaded += 1
            else:
                cached += 1
    return {"downloaded": downloaded, "already_cached": cached}


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
        limit = None if do_download else download_sample
        dl = download_records(records, cfg.cache_dir, delay=cfg.request_delay, limit=limit)
        summary["download"] = dl
        write_summary(out_dir, summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 2 harvest for the public_health pilot.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default="data/harvest", type=Path)
    p.add_argument("--contact", default="")
    p.add_argument("--download", action="store_true", help="download all chosen derivatives")
    p.add_argument("--download-sample", type=int, default=None, help="download only the first N")
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
    if not args.contact and not args.offline:
        cfg = load_pilot(args.config)
        if not cfg.contact:
            print(
                "Refusing to harvest without a contact for the User-Agent. Pass "
                "--contact you@example.com, set harvest.user_agent_contact in the "
                "config, or use --offline.",
                file=sys.stderr,
            )
            return 2
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
