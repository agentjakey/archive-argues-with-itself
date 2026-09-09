"""Cheap discovery and sizing pass, before any full scrape crawl.

Phase-1 and the first attempt at this pass both showed the same failure: the
scrape API (services/search/v1/scrape), under repeated use, stops honoring the
query and returns a fixed canned payload (a large baseline total, generic
non-Canadian items). Sizing built on that is worthless.

So this module does NOT size with the scrape API. It uses two surfaces that are
reliable here:

  - advancedsearch.php, which returns response.numFound for a query (sizing) and
    real matching identifiers (sampling). A nonsense-term canary confirms it is
    honoring the query before we trust any number.
  - the metadata API (metadata/{id}), to learn which collections real items
    belong to, their scanning center, and whether they actually carry an OCR
    derivative.

It answers four questions with real numbers, then stops:
  1. Which collections do real Canadian government items actually live in?
  2. How large is each of those collections (all items, and texts only)?
  3. Can each candidate topic clear the 2500-item floor, before we crawl?
  4. Do the items actually have usable OCR text, or is mediatype:texts a bluff?

Every count comes from a real API call, guarded by a throttle canary. Nothing is
guessed, and a throttled or canned response aborts the run instead of being
cached. Reuses the caching, backoff, and User-Agent from explore.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import tomllib
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.harvest import explore
from archive_debugger.harvest.explore import (
    ScrapeError,
    Transport,
    default_transport,
    decade_label,
    item_year,
)

ADVANCEDSEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/"

# File formats that indicate a usable OCR derivative. DjVuTXT, Abbyy GZ, and OCR
# Search Text carry plain text we would index; hOCR/chOCR/Djvu XML carry
# positional OCR.
OCR_TEXT_FORMATS = ("DjVuTXT", "Abbyy GZ", "OCR Search Text")
OCR_POSITIONAL_FORMATS = ("hOCR", "chOCR", "Djvu XML")
OCR_ALL_FORMATS = OCR_TEXT_FORMATS + OCR_POSITIONAL_FORMATS

# The confirmed Canadian Government Publications portal collection.
CONFIRMED_CANADA_COLLECTION = "governmentpublications"

# A term no real item contains, used to detect a throttled/canned search that
# ignores the query. A healthy search returns ~0 for this.
CANARY_TERM = "zzqxnonexistentterm42"
CANARY_MAX = 5

# Plausible bounds for the gov-publications baseline count; outside this range we
# assume a canned/throttled response and abort.
BASELINE_MIN = 50_000
BASELINE_MAX = 300_000

log = logging.getLogger("harvest.discover")


class ThrottleError(ScrapeError):
    """Raised when a search response looks canned/throttled rather than real."""


# --------------------------------------------------------------------------- #
# Cached GET (reuses explore's cache + backoff)
# --------------------------------------------------------------------------- #


def cached_get_json(
    url: str,
    *,
    cache_dir: Path,
    transport: Transport,
    sleeper: Callable[[float], None],
    rng: random.Random,
    headers: dict,
    page_delay: float = 1.0,
    offline: bool = False,
) -> dict:
    cached = explore.load_cache(cache_dir, url)
    if cached is not None:
        return cached
    if offline:
        raise ScrapeError(f"offline mode and cache miss for {url}")
    data = explore.fetch_with_retries(
        url, headers, transport=transport, sleeper=sleeper, rng=rng
    )
    explore.save_cache(cache_dir, url, data)
    sleeper(page_delay)  # politeness only on real network calls
    return data


def metadata_url(identifier: str) -> str:
    return METADATA_URL + urllib.parse.quote(identifier)


def advancedsearch_url(query: str, *, rows: int, fields: tuple[str, ...] = ()) -> str:
    params = [("q", query), ("rows", str(rows)), ("output", "json")]
    params += [("fl[]", f) for f in fields]
    return f"{ADVANCEDSEARCH_URL}?{urllib.parse.urlencode(params)}"


# --------------------------------------------------------------------------- #
# Search surface (advancedsearch.php)
# --------------------------------------------------------------------------- #


def _advancedsearch(query: str, *, rows: int, fields: tuple[str, ...], ctx: dict) -> dict:
    data = cached_get_json(advancedsearch_url(query, rows=rows, fields=fields), **ctx)
    response = data.get("response")
    if response is None:
        raise ScrapeError(f"advancedsearch returned no response for: {query}")
    return response


def count(query: str, *, ctx: dict) -> int:
    return _advancedsearch(query, rows=0, fields=(), ctx=ctx).get("numFound", 0)


def sample_identifiers(query: str, rows: int, *, ctx: dict) -> list[str]:
    docs = _advancedsearch(query, rows=rows, fields=("identifier", "year"), ctx=ctx).get("docs", [])
    return [d["identifier"] for d in docs if d.get("identifier")]


def assert_healthy(base_clause: str, *, ctx: dict) -> int:
    """Confirm the search surface is honoring queries. Returns the baseline
    count. Raises ThrottleError on a canned/throttled response."""
    canary = count(f"{base_clause} AND {CANARY_TERM}", ctx=ctx)
    if canary > CANARY_MAX:
        raise ThrottleError(
            f"canary term returned {canary} (> {CANARY_MAX}); search is not "
            "honoring the query (throttled/canned). Aborting before caching garbage."
        )
    baseline = count(base_clause, ctx=ctx)
    if not (BASELINE_MIN <= baseline <= BASELINE_MAX):
        raise ThrottleError(
            f"baseline count {baseline} for {base_clause} is outside the plausible "
            f"range [{BASELINE_MIN}, {BASELINE_MAX}]; likely canned. Aborting."
        )
    return baseline


# --------------------------------------------------------------------------- #
# Metadata surface + pure helpers
# --------------------------------------------------------------------------- #


def fetch_metadata(identifier: str, *, ctx: dict) -> dict:
    return cached_get_json(metadata_url(identifier), **ctx)


def collections_of(meta: dict) -> list[str]:
    value = meta.get("metadata", {}).get("collection")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def scanningcenter_of(meta: dict) -> Optional[str]:
    return meta.get("metadata", {}).get("scanningcenter")


def meta_year(meta: dict) -> Optional[int]:
    return item_year(meta.get("metadata", {}))


def file_formats(meta: dict) -> set[str]:
    return {f.get("format") for f in meta.get("files", []) if f.get("format")}


def ocr_flags(meta: dict) -> dict:
    formats = file_formats(meta)
    flags = {fmt: (fmt in formats) for fmt in OCR_ALL_FORMATS}
    flags["has_usable_text"] = any(fmt in formats for fmt in OCR_TEXT_FORMATS)
    flags["has_any_ocr"] = any(fmt in formats for fmt in OCR_ALL_FORMATS)
    return flags


# --------------------------------------------------------------------------- #
# Discovery steps
# --------------------------------------------------------------------------- #


def discover_collections(identifiers: list[str], *, ctx: dict) -> dict:
    col_freq: Counter = Counter()
    center_freq: Counter = Counter()
    for ident in identifiers:
        meta = fetch_metadata(ident, ctx=ctx)
        col_freq.update(collections_of(meta))
        center = scanningcenter_of(meta)
        if center:
            center_freq[center] += 1
    return {
        "sample_size": len(identifiers),
        "collection_frequency": col_freq,
        "scanningcenter_frequency": center_freq,
    }


def size_collection(collection: str, *, ctx: dict) -> dict:
    total = count(f"collection:{collection}", ctx=ctx)
    texts = count(f"mediatype:texts AND collection:{collection}", ctx=ctx)
    return {"collection": collection, "total_items": total, "texts_items": texts}


def size_topic(term_query: str, canada_clause: str, *, ctx: dict) -> int:
    return count(f"mediatype:texts AND {canada_clause} AND ({term_query})", ctx=ctx)


def ocr_spotcheck(identifiers: list[str], *, ctx: dict) -> dict:
    n = usable = any_ocr = undated = 0
    fmt_counts: Counter = Counter()
    decade_counts: Counter = Counter()
    for ident in identifiers:
        meta = fetch_metadata(ident, ctx=ctx)
        flags = ocr_flags(meta)
        n += 1
        usable += 1 if flags["has_usable_text"] else 0
        any_ocr += 1 if flags["has_any_ocr"] else 0
        for fmt in OCR_ALL_FORMATS:
            if flags[fmt]:
                fmt_counts[fmt] += 1
        year = meta_year(meta)
        if year is None:
            undated += 1
        else:
            decade_counts[decade_label(year)] += 1
    return {
        "sample_size": n,
        "with_usable_text": usable,
        "with_usable_text_pct": explore._pct(usable, n),
        "with_any_ocr": any_ocr,
        "with_any_ocr_pct": explore._pct(any_ocr, n),
        "format_counts": dict(fmt_counts),
        "decade_counts": dict(sorted(decade_counts.items())),
        "undated": undated,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _load_candidates(config_path: Path) -> list[explore.Candidate]:
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)
    return [
        explore.Candidate(name=c["name"], query=c["query"])
        for c in raw["audit"].get("candidates", [])
    ]


def run_discovery(
    config_path: Path,
    out_dir: Path,
    cache_dir: Path,
    *,
    contact: str,
    sample_size: int = 20,
    ocr_sample_size: int = 25,
    transport: Transport = default_transport,
    sleeper: Callable[[float], None] = time.sleep,
    rng: Optional[random.Random] = None,
    page_delay: float = 1.0,
    offline: bool = False,
) -> dict:
    rng = rng or random.Random(0)
    ctx = {
        "cache_dir": cache_dir,
        "transport": transport,
        "sleeper": sleeper,
        "rng": rng,
        "headers": {"User-Agent": explore.user_agent(contact), "Accept": "application/json"},
        "page_delay": page_delay,
        "offline": offline,
    }
    candidates = _load_candidates(config_path)
    base_clause = f"collection:{CONFIRMED_CANADA_COLLECTION}"

    # Guard: confirm the search surface is honoring queries before trusting it.
    baseline = assert_healthy(base_clause, ctx=ctx)
    log.info("search healthy; baseline %s = %s", base_clause, baseline)

    # Step 1: discover collections from a real topical housing sample.
    housing = next((c for c in candidates if "housing" in c.name), candidates[0])
    housing_query = f"mediatype:texts AND {base_clause} AND ({housing.query})"
    sample_ids = sample_identifiers(housing_query, 100, ctx=ctx)[:sample_size]
    discovery = discover_collections(sample_ids, ctx=ctx)

    # Step 2: size every discovered collection.
    discovered = [c for c, _ in discovery["collection_frequency"].most_common()]
    sizes = [size_collection(col, ctx=ctx) for col in discovered]
    union_clause = "collection:(" + " OR ".join(discovered) + ")" if discovered else base_clause

    # Step 3: size each topic against the Canada-scoped clause (base and union).
    topic_sizes = []
    for cand in candidates:
        base_count = size_topic(cand.query, base_clause, ctx=ctx)
        union_count = size_topic(cand.query, union_clause, ctx=ctx)
        topic_sizes.append(
            {
                "topic": cand.name,
                "base_clause_count": base_count,
                "union_clause_count": union_count,
                "reaches_2500_base": base_count >= explore.TARGET_ITEMS,
                "reaches_2500_union": union_count >= explore.TARGET_ITEMS,
            }
        )

    # Step 4: OCR spot check per topic on a real topical sample.
    ocr = {}
    for cand in candidates:
        topic_query = f"mediatype:texts AND {base_clause} AND ({cand.query})"
        ids = sample_identifiers(topic_query, 100, ctx=ctx)[:ocr_sample_size]
        ocr[cand.name] = ocr_spotcheck(ids, ctx=ctx)

    result = {
        "search_surface": "advancedsearch.php",
        "base_clause": base_clause,
        "base_clause_count": baseline,
        "union_clause": union_clause,
        "discovery": {
            "sample_size": discovery["sample_size"],
            "collection_frequency": dict(discovery["collection_frequency"].most_common()),
            "scanningcenter_frequency": dict(discovery["scanningcenter_frequency"].most_common()),
        },
        "collection_sizes": sizes,
        "topic_sizes": topic_sizes,
        "ocr_spotcheck": ocr,
    }
    _write_reports(out_dir, result)
    return result


def _write_reports(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "discovery.json").open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    lines: list[str] = []
    lines.append("# Discovery and sizing pass")
    lines.append("")
    lines.append(f"Search surface: {result['search_surface']} (scrape API was throttled to a canned baseline).")
    lines.append(f"Base Canada-scoped clause: `{result['base_clause']}` = {result['base_clause_count']} items.")
    lines.append("")
    lines.append("## 1. Collections found in the housing sample")
    lines.append(f"Sample size: {result['discovery']['sample_size']} real topical items.")
    lines.append("")
    lines.append("| collection | appears in N items |")
    lines.append("| --- | ---: |")
    for col, freq in result["discovery"]["collection_frequency"].items():
        lines.append(f"| {col} | {freq} |")
    lines.append("")
    lines.append("Scanning centers: " + ", ".join(
        f"{c} ({n})" for c, n in result["discovery"]["scanningcenter_frequency"].items()
    ))
    lines.append("")
    lines.append("## 2. Collection sizes")
    lines.append("")
    lines.append("| collection | total items | texts items |")
    lines.append("| --- | ---: | ---: |")
    for s in result["collection_sizes"]:
        lines.append(f"| {s['collection']} | {s['total_items']} | {s['texts_items']} |")
    lines.append("")
    lines.append("## 3. Topic sizing (can each clear 2500?)")
    lines.append("")
    lines.append("| topic | count in base clause | reaches 2500 | count in union clause | reaches 2500 |")
    lines.append("| --- | ---: | :---: | ---: | :---: |")
    for t in result["topic_sizes"]:
        lines.append(
            f"| {t['topic']} | {t['base_clause_count']} | "
            f"{'yes' if t['reaches_2500_base'] else 'no'} | "
            f"{t['union_clause_count']} | {'yes' if t['reaches_2500_union'] else 'no'} |"
        )
    lines.append("")
    lines.append("## 4. OCR-derivative spot check")
    lines.append("")
    lines.append("| topic | sample | usable text % | any OCR % | undated | decade distribution |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for topic, o in result["ocr_spotcheck"].items():
        decades = ", ".join(f"{d}:{n}" for d, n in o["decade_counts"].items())
        lines.append(
            f"| {topic} | {o['sample_size']} | {o['with_usable_text_pct']} | "
            f"{o['with_any_ocr_pct']} | {o['undated']} | {decades} |"
        )
    lines.append("")
    (out_dir / "discovery.md").write_text("\n".join(lines), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cheap discovery + sizing pass (no full crawl).")
    parser.add_argument("--config", default="config/audit_candidates.toml", type=Path)
    parser.add_argument("--out", default="reports/coverage_audit", type=Path)
    parser.add_argument("--cache-dir", default="raw/discovery_cache", type=Path)
    parser.add_argument("--contact", default="")
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--ocr-sample-size", type=int, default=25)
    parser.add_argument("--page-delay", type=float, default=1.0)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.contact and not args.offline:
        print(
            "Refusing to run discovery without a contact for the User-Agent. "
            "Pass --contact you@example.com or use --offline.",
            file=sys.stderr,
        )
        return 2
    try:
        result = run_discovery(
            args.config,
            args.out,
            args.cache_dir,
            contact=args.contact,
            sample_size=args.sample_size,
            ocr_sample_size=args.ocr_sample_size,
            page_delay=args.page_delay,
            offline=args.offline,
        )
    except ThrottleError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        return 3
    print(f"Discovery complete. Topics sized: {len(result['topic_sizes'])}.")
    print(f"See {args.out / 'discovery.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
