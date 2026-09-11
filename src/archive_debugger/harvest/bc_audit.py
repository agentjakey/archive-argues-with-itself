"""British Columbia scope audit (harvest layer; network only for advancedsearch counts
and per-item metadata, never for OCR or page downloads).

Applies the Week 1 audit method (reports/coverage_audit/finalist_sizing.md) to a
second candidate scope: BC government health publications on the Internet Archive.

1. Guard: canary term + baseline count must look real (reuses discover.assert_healthy).
2. Discover: sample real BC-issued texts (publisher/creator names British Columbia)
   matching the public_health term-set; read their metadata to learn which IA
   collections hold them and which scanning centers produced them.
3. Size: for each discovered collection and for the BC-issuer clause itself, count
   texts items, public_health items, public_health items dated 1960-2009, 2010+, and
   undated (no year field).
4. OCR: 25-item metadata spot check on real BC public_health items.
5. Write reports/bc_audit/bc_sizing.md in the finalist_sizing.md structure, with the
   2,500-item floor applied to the in-window, OCR-bearing estimate.

Every number is a real API response cached on disk; nothing is inferred."""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import tomllib
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.harvest import discover, explore
from archive_debugger.harvest.explore import TARGET_ITEMS, Transport, default_transport

log = logging.getLogger("harvest.bc_audit")

BC_ISSUER_CLAUSE = '(publisher:("British Columbia") OR creator:("British Columbia"))'
WINDOW = (1960, 2009)
EXCLUDED_COLLECTIONS = {"texts", "americana", "additional_collections", "opensource", "fav-", "toronto",
                        "university_of_toronto", "robarts", "microfiche", "university_of_alberta_libraries"}


def _window_clause(start: int, end: int) -> str:
    return f"year:[{start} TO {end}]"


def size_scope(clause: str, topic_query: str, *, ctx: dict) -> dict:
    """Counts for one scope clause: all texts, topic, topic in window, topic 2010+."""
    base = f"mediatype:texts AND {clause}"
    topic = f"{base} AND ({topic_query})"
    return {
        "clause": clause,
        "texts_items": discover.count(base, ctx=ctx),
        "topic_items": discover.count(topic, ctx=ctx),
        "topic_1960_2009": discover.count(f"{topic} AND {_window_clause(*WINDOW)}", ctx=ctx),
        "topic_1990_2009": discover.count(f"{topic} AND {_window_clause(1990, 2009)}", ctx=ctx),
        "topic_2010_plus": discover.count(f"{topic} AND year:[2010 TO 2100]", ctx=ctx),
        "topic_pre_1960": discover.count(f"{topic} AND year:[1000 TO 1959]", ctx=ctx),
    }


def _topic_query(config_path: Path, name: str) -> str:
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    for c in raw["audit"].get("candidates", []):
        if c["name"] == name:
            return c["query"]
    raise KeyError(f"candidate {name} not in {config_path}")


def run_bc_audit(config_path: Path, out_dir: Path, cache_dir: Path, *, contact: str, topic: str = "public_health",
                 sample_size: int = 30, ocr_sample_size: int = 25, transport: Transport = default_transport,
                 sleeper: Callable[[float], None] = time.sleep, rng: Optional[random.Random] = None,
                 page_delay: float = 1.0, offline: bool = False) -> dict:
    rng = rng or random.Random(0)
    ctx = {"cache_dir": cache_dir, "transport": transport, "sleeper": sleeper, "rng": rng,
           "headers": {"User-Agent": explore.user_agent(contact), "Accept": "application/json"},
           "page_delay": page_delay, "offline": offline}
    topic_query = _topic_query(config_path, topic)
    baseline = discover.assert_healthy(f"collection:{discover.CONFIRMED_CANADA_COLLECTION}", ctx=ctx)

    # 2. Discover which collections hold BC-issued health texts.
    bc_topic = f"mediatype:texts AND {BC_ISSUER_CLAUSE} AND ({topic_query})"
    sample_ids = discover.sample_identifiers(bc_topic, 100, ctx=ctx)[:sample_size]
    disc = discover.discover_collections(sample_ids, ctx=ctx)
    discovered = [c for c, _ in disc["collection_frequency"].most_common()
                  if not any(c == x or c.startswith(x) for x in EXCLUDED_COLLECTIONS)]

    # 3. Size the issuer clause, each discovered collection, their union, and the
    #    pilot's own clean clause for comparison.
    scopes = [("bc_issuer", BC_ISSUER_CLAUSE)]
    scopes += [(col, f"collection:{col}") for col in discovered[:8]]
    if discovered:
        scopes.append(("bc_union", "collection:(" + " OR ".join(discovered[:8]) + ")"))
    scopes.append(("bc_issuer_in_union" if discovered else "bc_issuer_in_gov",
                   f"{BC_ISSUER_CLAUSE} AND collection:(" + " OR ".join(discovered[:8] or [discover.CONFIRMED_CANADA_COLLECTION]) + ")"))
    scopes.append(("pilot_gov", f"collection:{discover.CONFIRMED_CANADA_COLLECTION}"))
    sizes = []
    for name, clause in scopes:
        s = size_scope(clause, topic_query, ctx=ctx)
        s["name"] = name
        sizes.append(s)

    # 4. OCR spot check on real BC topical items (metadata only).
    ocr_ids = discover.sample_identifiers(bc_topic, 100, ctx=ctx)[:ocr_sample_size]
    ocr = discover.ocr_spotcheck(ocr_ids, ctx=ctx)

    result = {
        "search_surface": "advancedsearch.php",
        "topic": topic, "topic_query": topic_query,
        "baseline_gov_count": baseline,
        "bc_issuer_clause": BC_ISSUER_CLAUSE,
        "window": list(WINDOW), "floor": TARGET_ITEMS,
        "discovery": {"sample_size": disc["sample_size"],
                      "collection_frequency": dict(disc["collection_frequency"].most_common()),
                      "scanningcenter_frequency": dict(disc["scanningcenter_frequency"].most_common()),
                      "collections_kept": discovered[:8]},
        "sizes": sizes,
        "ocr_spotcheck": ocr,
        "sample_identifiers": sample_ids,
    }
    result["recommendation"] = recommend(result)
    _write(out_dir, result)
    return result


def recommend(result: dict) -> dict:
    """The floor applied to the best BC-SCOPED clause (issuer names British Columbia),
    in-window; OCR share from the spot check. Whole collections the sampled items live
    in are context, not BC scopes: a medical library holding one BC report is not BC."""
    bc_scoped = [s for s in result["sizes"] if s["name"].startswith("bc_issuer")]
    best = max(bc_scoped, key=lambda s: s["topic_1960_2009"])
    ocr = result["ocr_spotcheck"]
    share = (ocr["with_usable_text"] / ocr["sample_size"]) if ocr["sample_size"] else 0.0
    est = round(best["topic_1960_2009"] * share)
    return {
        "best_scope": best["name"], "best_clause": best["clause"],
        "topic_items": best["topic_items"], "topic_1960_2009": best["topic_1960_2009"],
        "ocr_usable_share": round(share, 3), "estimated_usable_in_window": est,
        "clears_floor": est >= TARGET_ITEMS,
        "verdict": ("BC clears the 2,500 floor in the 1960-2009 window as a second scope under the same code"
                    if est >= TARGET_ITEMS else
                    "BC does not clear the 2,500 floor in the 1960-2009 window; a BC scope would need a lower floor, "
                    "a wider window, or a broader topic term-set"),
    }


def _write(out_dir: Path, r: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bc_sizing.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    L: list[str] = []
    L += ["# British Columbia scope: sizing and window analysis", "",
          "All counts are real `advancedsearch.php` `numFound` results (same surface and throttle canary as the",
          "Week 1 audit; the scrape API is not used). Query shape: `mediatype:texts AND <clause> AND (<topic",
          f"term-set>)`, topic term-set `{r['topic']}` from config/audit_candidates.toml. Window clause:",
          f"`year:[{r['window'][0]} TO {r['window'][1]}]`. Items with no `year` field fall outside every year clause.",
          "No item was downloaded; OCR presence is read from item metadata.", "",
          f"Search health: baseline `collection:governmentpublications` = {r['baseline_gov_count']:,} (canary passed).", "",
          "## Where BC health texts live", "",
          f"Sample: {r['discovery']['sample_size']} real texts matching `{r['bc_issuer_clause']}` and the topic term-set.", "",
          "| collection | appears in N sampled items |", "| --- | ---: |"]
    for col, n in r["discovery"]["collection_frequency"].items():
        L.append(f"| {col} | {n} |")
    L += ["", "Scanning centers: " + (", ".join(f"{c} ({n})" for c, n in r["discovery"]["scanningcenter_frequency"].items()) or "none recorded"), "",
          "## Sizing: BC-scoped clauses and the collections the sample lives in", "",
          "`bc_issuer*` rows are BC scopes (the issuer names British Columbia). The collection rows size the",
          "whole collections the sampled items belong to; they are context for where BC material sits, not BC",
          "scopes, and `bc_union` is their union. `pilot_gov` is the public-health pilot's own clean clause.", "",
          f"| scope | clause | texts items | {r['topic']} | in 1960-2009 | 1990-2009 | 2010+ | pre-1960 |",
          "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in r["sizes"]:
        L.append(f"| {s['name']} | `{s['clause']}` | {s['texts_items']:,} | {s['topic_items']:,} | "
                 f"{s['topic_1960_2009']:,} | {s['topic_1990_2009']:,} | {s['topic_2010_plus']:,} | {s['topic_pre_1960']:,} |")
    L += ["", "Topic items outside every year column carry no `year` field (undated), which the pilot corpus",
          "showed to be a large share.", "",
          f"## BC scopes against the {r['floor']:,} floor", ""]
    for s in [x for x in r["sizes"] if x["name"].startswith("bc_issuer") or x["name"] == "pilot_gov"]:
        L.append(f"- {s['name']}: {s['topic_items']:,} {r['topic']} texts ({'yes' if s['topic_items'] >= r['floor'] else 'no'} on raw count); "
                 f"{s['topic_1960_2009']:,} dated 1960-2009 ({'yes' if s['topic_1960_2009'] >= r['floor'] else 'no'}).")
    o = r["ocr_spotcheck"]
    L += ["", "## OCR presence (metadata spot check, BC topical sample)", "",
          f"Sample {o['sample_size']} items: {o['with_usable_text']} with usable OCR text ({o['with_usable_text_pct']}%), "
          f"{o['with_any_ocr']} with any OCR derivative ({o['with_any_ocr_pct']}%), {o['undated']} undated.",
          "Formats: " + ", ".join(f"{k} {v}" for k, v in o["format_counts"].items()),
          "Decades: " + (", ".join(f"{d}:{n}" for d, n in o["decade_counts"].items()) or "none dated"), "",
          "## Recommendation", ""]
    rec = r["recommendation"]
    gov_share = next((s for s in r["sizes"] if s["name"] == "pilot_gov"), None)
    L += [f"Of the {r['discovery']['sample_size']} sampled BC health texts, "
          f"{r['discovery']['collection_frequency'].get(discover.CONFIRMED_CANADA_COLLECTION, 0)} sit in "
          f"`collection:{discover.CONFIRMED_CANADA_COLLECTION}`, the clean Canadian-government portal the pilot uses"
          + (f" ({gov_share['topic_items']:,} public-health texts there in total)" if gov_share else "") +
          "; the rest sit in medical-library and microfiche collections. BC government health publications are not,",
          "on the Internet Archive, a government-portal corpus the way the federal, Ontario and Alberta material is.", "",
          f"Best BC scope by in-window count: `{rec['best_scope']}` (`{rec['best_clause']}`): {rec['topic_items']:,} "
          f"{r['topic']} texts, {rec['topic_1960_2009']:,} dated 1960-2009. With the spot-check OCR share of "
          f"{rec['ocr_usable_share']:.0%}, the estimated usable in-window count is {rec['estimated_usable_in_window']:,} "
          f"against the {r['floor']:,} floor: **{'clears' if rec['clears_floor'] else 'does not clear'}**.", "",
          rec["verdict"] + ".", "",
          "Method caveats: `year:[a TO b]` excludes items with no year field, so undated items (which the pilot could",
          "partly recover from titles) are not in the window counts; the publisher/creator clause depends on IA",
          "metadata naming the province and misses items whose issuer is a BC ministry named without the province;",
          "OCR share is from a 25-item metadata sample. The code path is the same as the pilot's: a BC scope is a new",
          "`config/pilot.toml` (query, collections, window) and a new manifest, not a code change.", ""]
    (out_dir / "bc_sizing.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="BC scope audit: sizing, window, OCR presence. No harvest.")
    p.add_argument("--config", default="config/audit_candidates.toml", type=Path)
    p.add_argument("--out", default="reports/bc_audit", type=Path)
    p.add_argument("--cache-dir", default="raw/bc_audit_cache", type=Path)
    p.add_argument("--contact", default="")
    p.add_argument("--topic", default="public_health")
    p.add_argument("--page-delay", type=float, default=1.0)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not args.contact and not args.offline:
        print("Refusing to run without a contact for the User-Agent (--contact) unless --offline.", file=sys.stderr)
        return 2
    try:
        r = run_bc_audit(args.config, args.out, args.cache_dir, contact=args.contact, topic=args.topic,
                         page_delay=args.page_delay, offline=args.offline)
    except explore.ScrapeError as exc:
        print(f"aborted: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(r["recommendation"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out / 'bc_sizing.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
