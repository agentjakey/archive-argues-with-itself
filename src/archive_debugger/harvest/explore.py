"""Week 1 coverage audit over Internet Archive Canadian government collections.

This module is the network layer for the pilot-topic audit. It does one job:
given a few candidate civic-topic queries and a set of Canadian government
collections, it pages through the Internet Archive scrape API, caches every page
on disk, and produces coverage tables (decade x jurisdiction x document type) so
a human can choose the topic and time window with real numbers in front of them.

It does NOT build the retrieval index. It does NOT fetch page-level OCR text.
Those are later phases. Here we only read metadata to measure coverage.

Etiquette is enforced, not optional:
  - a descriptive User-Agent carrying a contact,
  - sequential requests (no concurrency),
  - exponential backoff with jitter on 429/503, honoring Retry-After,
  - an on-disk cache so a rerun makes zero network calls.

Everything written to reports/ is computed from fetched data. Nothing here
fabricates counts, dates, or coverage claims. Where a value is unknown (undated
item, unrecognized issuer), it is labeled "Unknown" and counted as such.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import sys
import time
import tomllib
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterable, NamedTuple, Optional

SCRAPE_URL = "https://archive.org/services/search/v1/scrape"

# Minimum longitudinal signal: a decade "counts" toward longitudinal coverage
# only if it holds at least this many items. Kept explicit so the threshold is
# visible rather than buried.
DECADE_MIN_ITEMS = 25

# Success metric from the proposal.
TARGET_ITEMS = 2500

# Recency cutoffs used to flag the pre-2000 risk.
RECENT_YEAR = 2000
VERY_RECENT_YEAR = 2015

log = logging.getLogger("harvest.explore")


class ScrapeError(RuntimeError):
    """Raised when the scrape API cannot be read after retries."""


class HttpResponse(NamedTuple):
    status: int
    headers: dict  # header names lowercased
    text: str


# A transport takes (url, headers, timeout_seconds) and returns an HttpResponse.
# The default one uses requests; tests inject a fake so no network is touched.
Transport = Callable[[str, dict, float], HttpResponse]


def default_transport(url: str, headers: dict, timeout: float) -> HttpResponse:
    """Real network transport. requests is imported here so that importing this
    module, and running the unit tests, does not require requests installed."""
    import requests

    resp = requests.get(url, headers=headers, timeout=timeout)
    lowered = {k.lower(): v for k, v in resp.headers.items()}
    return HttpResponse(resp.status_code, lowered, resp.text)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass
class Candidate:
    name: str
    query: str


@dataclass
class AuditConfig:
    fields: str
    count: int
    max_items: int
    mediatype: str
    collections: list[str]
    contact: str
    candidates: list[Candidate] = field(default_factory=list)


def load_config(path: Path) -> AuditConfig:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    audit = raw["audit"]
    cols_section = audit.get("collections", {})
    collections = list(cols_section.get("confirmed", [])) + list(
        cols_section.get("candidate", [])
    )
    if not collections:
        raise ValueError("no collections configured under [audit.collections]")
    # [[audit.candidates]] tables land under audit["candidates"].
    candidates = [
        Candidate(name=c["name"], query=c["query"])
        for c in audit.get("candidates", [])
    ]
    if not candidates:
        raise ValueError("no [[audit.candidates]] configured")
    return AuditConfig(
        fields=audit["fields"],
        count=int(audit.get("count", 100)),
        max_items=int(audit.get("max_items", 0)),
        mediatype=audit.get("mediatype", "texts"),
        collections=collections,
        contact=audit.get("contact", ""),
        candidates=candidates,
    )


# --------------------------------------------------------------------------- #
# Query and URL construction
# --------------------------------------------------------------------------- #


def build_query(candidate_query: str, collections: list[str], mediatype: str) -> str:
    parts = []
    if mediatype:
        parts.append(f"mediatype:{mediatype}")
    cols = " OR ".join(collections)
    parts.append(f"collection:({cols})")
    parts.append(f"({candidate_query})")
    return " AND ".join(parts)


def build_url(query: str, fields: str, count: int, cursor: Optional[str]) -> str:
    params = {"q": query, "fields": fields, "count": str(count)}
    if cursor:
        params["cursor"] = cursor
    return f"{SCRAPE_URL}?{urllib.parse.urlencode(params)}"


def user_agent(contact: str) -> str:
    from archive_debugger import __version__

    return (
        f"archive-argues-with-itself/{__version__} "
        f"(Week 1 coverage audit; "
        f"+https://github.com/agentjakey/archive-argues-with-itself; "
        f"contact: {contact})"
    )


# --------------------------------------------------------------------------- #
# On-disk cache
# --------------------------------------------------------------------------- #


def cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def load_cache(cache_dir: Path, url: str) -> Optional[dict]:
    path = cache_path(cache_dir, url)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_cache(cache_dir: Path, url: str, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, url)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Fetch with backoff
# --------------------------------------------------------------------------- #


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Return seconds to wait from a Retry-After header, or None if absent or
    unparseable. Supports both the delta-seconds and HTTP-date forms."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, delta)


def fetch_with_retries(
    url: str,
    headers: dict,
    *,
    transport: Transport,
    sleeper: Callable[[float], None],
    rng: random.Random,
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    timeout: float = 30.0,
) -> dict:
    """GET url, retrying 429/503 with exponential backoff plus jitter, honoring
    Retry-After when present. Returns parsed JSON. Raises ScrapeError otherwise."""
    attempt = 0
    while True:
        resp = transport(url, headers, timeout)
        if resp.status == 200:
            data = json.loads(resp.text)
            if isinstance(data, dict) and data.get("error"):
                raise ScrapeError(f"scrape API error for {url}: {data['error']}")
            return data
        if resp.status in (429, 503) and attempt < max_retries:
            retry_after = parse_retry_after(resp.headers.get("retry-after"))
            if retry_after is not None:
                delay = retry_after
            else:
                delay = min(max_delay, base_delay * (2 ** attempt))
            delay += rng.uniform(0.0, base_delay)  # jitter
            log.warning(
                "HTTP %s on attempt %s; backing off %.1fs", resp.status, attempt + 1, delay
            )
            sleeper(delay)
            attempt += 1
            continue
        raise ScrapeError(f"HTTP {resp.status} for {url}: {resp.text[:200]}")


def scrape_all(
    query: str,
    *,
    fields: str,
    count: int,
    cache_dir: Path,
    transport: Transport,
    sleeper: Callable[[float], None],
    rng: random.Random,
    headers: dict,
    max_items: int = 0,
    page_delay: float = 1.5,
    offline: bool = False,
) -> tuple[list[dict], dict]:
    """Page through the scrape API with cursor pagination. Reads the on-disk
    cache first; a fully cached query makes zero network calls and incurs no
    polite delay. Returns (items, meta) where meta carries total and page count."""
    items: list[dict] = []
    cursor: Optional[str] = None
    pages = 0
    total: Optional[int] = None
    while True:
        url = build_url(query, fields, count, cursor)
        cached = load_cache(cache_dir, url)
        if cached is not None:
            data = cached
        else:
            if offline:
                raise ScrapeError(f"offline mode and cache miss for {url}")
            data = fetch_with_retries(
                url, headers, transport=transport, sleeper=sleeper, rng=rng
            )
            save_cache(cache_dir, url, data)
            sleeper(page_delay)  # politeness only when we actually hit the network
        page_items = data.get("items", []) or []
        if total is None:
            total = data.get("total")
        items.extend(page_items)
        pages += 1
        cursor = data.get("cursor")
        if not cursor or not page_items:
            break
        if max_items and len(items) >= max_items:
            break
    if max_items:
        items = items[:max_items]
    return items, {"total": total, "pages": pages}


# --------------------------------------------------------------------------- #
# Normalization (best effort, honest about unknowns)
# --------------------------------------------------------------------------- #


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def item_year(item: dict) -> Optional[int]:
    """Prefer the numeric year field; fall back to parsing the date field. Return
    None when neither yields a plausible four-digit year."""
    year = item.get("year")
    if isinstance(year, int):
        return year
    if isinstance(year, str) and year[:4].isdigit():
        return int(year[:4])
    date = item.get("date")
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def decade_label(year: Optional[int]) -> str:
    if year is None:
        return "undated"
    return f"{(year // 10) * 10}s"


# Provinces and territories, checked against issuer text (publisher/creator/title).
_PROVINCE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("Ontario", ("ontario",)),
    ("Quebec", ("quebec", "quebec.", "province of quebec")),
    ("British Columbia", ("british columbia", "colombie-britannique")),
    ("Alberta", ("alberta",)),
    ("Manitoba", ("manitoba",)),
    ("Saskatchewan", ("saskatchewan",)),
    ("Nova Scotia", ("nova scotia",)),
    ("New Brunswick", ("new brunswick", "nouveau-brunswick")),
    ("Prince Edward Island", ("prince edward island",)),
    ("Newfoundland and Labrador", ("newfoundland", "labrador")),
    ("Yukon", ("yukon",)),
    ("Northwest Territories", ("northwest territories",)),
    ("Nunavut", ("nunavut",)),
]

# Conservative federal indicators, only consulted when no province matched.
_FEDERAL_PATTERNS: tuple[str, ...] = (
    "dominion of canada",
    "government of canada",
    "statistics canada",
    "statistique canada",
    "parliament of canada",
    "house of commons",
    "privy council",
    "royal commission",
    "agriculture canada",
    "canada. department",
    "canada, department",
)

# Known issuer sub-collection identifiers. The scanner collections (toronto,
# governmentpublications) are deliberately NOT used for jurisdiction, since they
# say who digitized the item, not who issued it.
_COLLECTION_JURISDICTION = {
    "ontla": "Ontario",
}


def jurisdiction(item: dict) -> str:
    """Best-effort issuing jurisdiction. Provinces first (more specific), then a
    small set of federal indicators, then known issuer sub-collections, else
    Unknown. Never guesses beyond these signals."""
    text = " ".join(
        [
            _as_text(item.get("publisher")),
            _as_text(item.get("creator")),
            _as_text(item.get("title")),
        ]
    ).lower()
    for label, needles in _PROVINCE_PATTERNS:
        if any(n in text for n in needles):
            return label
    for needle in _FEDERAL_PATTERNS:
        if needle in text:
            return "Federal"
    for col in item.get("collection", []) or []:
        if col in _COLLECTION_JURISDICTION:
            return _COLLECTION_JURISDICTION[col]
    return "Unknown"


# Document-type heuristics over the title, most specific first.
_DOCTYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Sessional paper", ("sessional paper",)),
    ("Debates/Hansard", ("debates", "hansard")),
    ("Census", ("census",)),
    ("Legislation/regulation", ("statutes", "regulation", "by-law", "bylaw", " act ")),
    ("Fiscal/estimates", ("estimates", "public accounts", "budget", "expenditure")),
    ("Annual report", ("annual report",)),
    ("Report", ("report",)),
    ("Study/survey", ("study", "survey", "analysis", "review")),
    ("Bulletin", ("bulletin", "circular")),
    ("Index/catalogue", ("index", "catalogue", "catalog")),
]


def doc_type(item: dict) -> str:
    title = _as_text(item.get("title")).lower()
    padded = f" {title} "
    for label, needles in _DOCTYPE_RULES:
        if any(n in padded for n in needles):
            return label
    return "Other/Unknown"


# --------------------------------------------------------------------------- #
# Tabulation
# --------------------------------------------------------------------------- #


@dataclass
class Coverage:
    name: str
    total_fetched: int
    reported_total: Optional[int]
    three_way: Counter  # (decade, jurisdiction, doc_type) -> count
    by_decade: Counter
    by_jurisdiction: Counter
    by_doc_type: Counter
    undated: int
    pre_recent: int  # year < RECENT_YEAR
    recent: int  # RECENT_YEAR <= year
    very_recent: int  # year >= VERY_RECENT_YEAR
    decades_with_signal: list[str]
    per_collection: Counter
    rows: list[dict]  # one inspectable row per item


def tabulate(name: str, items: list[dict], reported_total: Optional[int]) -> Coverage:
    three_way: Counter = Counter()
    by_decade: Counter = Counter()
    by_jurisdiction: Counter = Counter()
    by_doc_type: Counter = Counter()
    per_collection: Counter = Counter()
    undated = pre_recent = recent = very_recent = 0
    rows: list[dict] = []

    for item in items:
        year = item_year(item)
        dec = decade_label(year)
        juris = jurisdiction(item)
        dtype = doc_type(item)
        three_way[(dec, juris, dtype)] += 1
        by_decade[dec] += 1
        by_jurisdiction[juris] += 1
        by_doc_type[dtype] += 1
        for col in item.get("collection", []) or []:
            per_collection[col] += 1
        if year is None:
            undated += 1
        elif year < RECENT_YEAR:
            pre_recent += 1
        else:
            recent += 1
            if year >= VERY_RECENT_YEAR:
                very_recent += 1
        rows.append(
            {
                "identifier": item.get("identifier", ""),
                "year": "" if year is None else year,
                "decade": dec,
                "jurisdiction": juris,
                "doc_type": dtype,
                "title": _as_text(item.get("title")),
            }
        )

    decades_with_signal = sorted(
        d for d, c in by_decade.items() if d != "undated" and c >= DECADE_MIN_ITEMS
    )
    return Coverage(
        name=name,
        total_fetched=len(items),
        reported_total=reported_total,
        three_way=three_way,
        by_decade=by_decade,
        by_jurisdiction=by_jurisdiction,
        by_doc_type=by_doc_type,
        undated=undated,
        pre_recent=pre_recent,
        recent=recent,
        very_recent=very_recent,
        decades_with_signal=decades_with_signal,
        per_collection=per_collection,
        rows=rows,
    )


def _pct(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else round(100.0 * part / whole, 1)


def coverage_summary(cov: Coverage) -> dict:
    return {
        "candidate": cov.name,
        "items_fetched": cov.total_fetched,
        "reported_total": cov.reported_total,
        "reaches_target_2500": (cov.reported_total or cov.total_fetched) >= TARGET_ITEMS,
        "distinct_jurisdictions": sorted(
            j for j in cov.by_jurisdiction if j != "Unknown"
        ),
        "distinct_jurisdiction_count": len(
            [j for j in cov.by_jurisdiction if j != "Unknown"]
        ),
        "unknown_jurisdiction": cov.by_jurisdiction.get("Unknown", 0),
        "unknown_jurisdiction_pct": _pct(
            cov.by_jurisdiction.get("Unknown", 0), cov.total_fetched
        ),
        "undated": cov.undated,
        "undated_pct": _pct(cov.undated, cov.total_fetched),
        "pre_2000": cov.pre_recent,
        "pre_2000_pct": _pct(cov.pre_recent, cov.total_fetched),
        "year_2000_plus": cov.recent,
        "year_2000_plus_pct": _pct(cov.recent, cov.total_fetched),
        "year_2015_plus": cov.very_recent,
        "year_2015_plus_pct": _pct(cov.very_recent, cov.total_fetched),
        "decades_with_signal": cov.decades_with_signal,
        "decades_with_signal_count": len(cov.decades_with_signal),
        "top_doc_types": cov.by_doc_type.most_common(6),
        "top_collections": cov.per_collection.most_common(10),
    }


# --------------------------------------------------------------------------- #
# Output writers
# --------------------------------------------------------------------------- #


def write_csv(path: Path, header: list[str], rows: Iterable[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def write_candidate_outputs(out_dir: Path, cov: Coverage) -> None:
    name = cov.name

    three_way_rows = sorted(
        ([dec, juris, dtype, count] for (dec, juris, dtype), count in cov.three_way.items()),
        key=lambda r: (r[0], r[1], r[2]),
    )
    write_csv(
        out_dir / f"{name}__by_decade_jurisdiction_doctype.csv",
        ["decade", "jurisdiction", "doc_type", "count"],
        three_way_rows,
    )

    write_csv(
        out_dir / f"{name}__by_decade.csv",
        ["decade", "count"],
        sorted(([d, c] for d, c in cov.by_decade.items()), key=lambda r: r[0]),
    )

    write_csv(
        out_dir / f"{name}__by_jurisdiction.csv",
        ["jurisdiction", "count"],
        sorted(([j, c] for j, c in cov.by_jurisdiction.items()), key=lambda r: -r[1]),
    )

    write_csv(
        out_dir / f"{name}__items.csv",
        ["identifier", "year", "decade", "jurisdiction", "doc_type", "title"],
        [
            [r["identifier"], r["year"], r["decade"], r["jurisdiction"], r["doc_type"], r["title"]]
            for r in cov.rows
        ],
    )

    summary = coverage_summary(cov)
    with (out_dir / f"{name}__summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)


def write_audit_summary(out_dir: Path, coverages: list[Coverage], config: AuditConfig) -> None:
    """Write the human-facing comparison. Every statement here is derived from
    the computed coverage, not asserted independently."""
    lines: list[str] = []
    lines.append("# Coverage audit summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Collections searched: {', '.join(config.collections)}")
    lines.append(f"Mediatype: {config.mediatype}. Per-candidate item cap: {config.max_items or 'none'}.")
    lines.append(f"Longitudinal threshold: a decade counts if it holds >= {DECADE_MIN_ITEMS} items.")
    lines.append("")
    lines.append(
        "Note: mediatype:texts is used as the proxy for scanned-OCR coverage. "
        "Whether each item actually carries an OCR derivative is verified in the "
        "Week 2 harvest, not here."
    )
    lines.append("")

    lines.append("## Candidate comparison")
    lines.append("")
    lines.append(
        "| candidate | fetched | reported total | reaches 2500 | decades w/ signal | pre-2000 | 2000+ | 2015+ | undated | jurisdictions |"
    )
    lines.append("| --- | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    summaries = {}
    for cov in coverages:
        s = coverage_summary(cov)
        summaries[cov.name] = s
        lines.append(
            "| {name} | {fetched} | {total} | {reach} | {dec} | {pre} ({prep}%) | {rec} ({recp}%) | {vr} ({vrp}%) | {und} ({undp}%) | {jur} |".format(
                name=cov.name,
                fetched=s["items_fetched"],
                total=s["reported_total"],
                reach="yes" if s["reaches_target_2500"] else "no",
                dec=s["decades_with_signal_count"],
                pre=s["pre_2000"],
                prep=s["pre_2000_pct"],
                rec=s["year_2000_plus"],
                recp=s["year_2000_plus_pct"],
                vr=s["year_2015_plus"],
                vrp=s["year_2015_plus_pct"],
                und=s["undated"],
                undp=s["undated_pct"],
                jur=s["distinct_jurisdiction_count"],
            )
        )
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    longitudinal = [
        s for s in summaries.values()
        if s["reaches_target_2500"] and s["decades_with_signal_count"] >= 4
    ]
    if longitudinal:
        best = max(longitudinal, key=lambda s: s["decades_with_signal_count"])
        lines.append(
            f"- Candidates with citable, longitudinal scanned-OCR coverage "
            f"(reaches {TARGET_ITEMS} and spans >= 4 decades with signal): "
            + ", ".join(sorted(s["candidate"] for s in longitudinal))
            + f". Strongest by decade span: {best['candidate']} "
            f"({best['decades_with_signal_count']} decades)."
        )
    else:
        lines.append(
            f"- No candidate both reaches {TARGET_ITEMS} items and spans >= 4 "
            "decades with signal. The pilot must narrow the topic, widen the "
            "collections, or lower the target. This is a result to report, not "
            "to paper over."
        )
    for s in summaries.values():
        reach = "reaches" if s["reaches_target_2500"] else "does NOT reach"
        lines.append(
            f"- {s['candidate']}: {reach} {TARGET_ITEMS} "
            f"(reported total {s['reported_total']}). "
            f"Recency risk: {s['pre_2000_pct']}% of fetched items are pre-2000, "
            f"only {s['year_2015_plus']} items ({s['year_2015_plus_pct']}%) are 2015 or later. "
            f"{s['undated']} undated ({s['undated_pct']}%). "
            f"{s['unknown_jurisdiction']} items ({s['unknown_jurisdiction_pct']}%) "
            "have unknown jurisdiction."
        )
    lines.append("")
    lines.append(
        "The proposal's example asks about 1995, 2005, and 2025. The 2015+ "
        "column above is the direct evidence for whether a recent comparison "
        "year is even supportable in this archive."
    )
    lines.append("")

    (out_dir / "AUDIT_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_audit(
    config: AuditConfig,
    out_dir: Path,
    cache_dir: Path,
    *,
    contact: str,
    transport: Transport = default_transport,
    sleeper: Callable[[float], None] = time.sleep,
    rng: Optional[random.Random] = None,
    page_delay: float = 1.5,
    offline: bool = False,
) -> list[Coverage]:
    rng = rng or random.Random()
    headers = {"User-Agent": user_agent(contact), "Accept": "application/json"}
    coverages: list[Coverage] = []
    for cand in config.candidates:
        query = build_query(cand.query, config.collections, config.mediatype)
        log.info("candidate %s: %s", cand.name, query)
        items, meta = scrape_all(
            query,
            fields=config.fields,
            count=config.count,
            cache_dir=cache_dir,
            transport=transport,
            sleeper=sleeper,
            rng=rng,
            headers=headers,
            max_items=config.max_items,
            page_delay=page_delay,
            offline=offline,
        )
        log.info(
            "candidate %s: fetched %s items (reported total %s, %s pages)",
            cand.name,
            len(items),
            meta.get("total"),
            meta.get("pages"),
        )
        cov = tabulate(cand.name, items, meta.get("total"))
        write_candidate_outputs(out_dir, cov)
        coverages.append(cov)
    write_audit_summary(out_dir, coverages, config)
    return coverages


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Week 1 Internet Archive coverage audit for the pilot topic."
    )
    parser.add_argument("--config", default="config/audit_candidates.toml", type=Path)
    parser.add_argument("--out", default="reports/coverage_audit", type=Path)
    parser.add_argument("--cache-dir", default="raw/scrape_cache", type=Path)
    parser.add_argument(
        "--contact",
        default="",
        help="contact string for the User-Agent (email or URL). Required unless --offline.",
    )
    parser.add_argument("--max-items", type=int, default=None, help="override per-candidate cap")
    parser.add_argument("--page-delay", type=float, default=1.5)
    parser.add_argument(
        "--offline", action="store_true", help="use cache only; fail on any cache miss"
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    if args.max_items is not None:
        config.max_items = args.max_items
    contact = args.contact or config.contact
    if not contact and not args.offline:
        print(
            "Refusing to run a live audit without a contact for the User-Agent. "
            "Pass --contact you@example.com or set contact in the config, or use "
            "--offline to run from cache.",
            file=sys.stderr,
        )
        return 2
    coverages = run_audit(
        config,
        args.out,
        args.cache_dir,
        contact=contact,
        page_delay=args.page_delay,
        offline=args.offline,
    )
    print(f"Wrote coverage tables for {len(coverages)} candidates to {args.out}")
    print(f"See {args.out / 'AUDIT_SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
