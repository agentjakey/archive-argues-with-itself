"""Phase 5 normalization: fill the normalized item columns and coverage_cells.

Local only, offline. Reads the raw columns from civic.db (never the harvest-layer
year, per N4) and writes date/jurisdiction/issuer/doc_type plus their *_method
companions. Then aggregates coverage_cells.

No imputation: year/decade/dated are set only when an explicit year is stated in
date_raw, or recovered strictly from an explicit year in the title. Everything
unknown stays unknown; nothing is guessed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from archive_debugger.ingest import db

YEAR_MIN, YEAR_MAX = 1850, 2025

# Small words kept lowercase when title-casing an ALLCAPS issuer surface.
_SMALL = {"of", "and", "for", "the", "to", "in", "on", "de", "et", "des", "du", "la", "le"}
_ANAPHORA = re.compile(
    r"^the\s+(dept\.?|department|branch|commission|committee|board|fund|plan|"
    r"foundation|council|agency|ministry|corporation|secretariat|division)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #


def load_jurisdiction_rules(path: Path):
    """Return (text_rules, collection_rules). text_rules is a specificity-sorted
    list of (pattern, jurisdiction); collection_rules maps collection id ->
    jurisdiction."""
    text: list[tuple[int, int, str, str]] = []
    collection: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            kind = row["kind"].strip()
            pattern = row["pattern"].strip().lower()
            jur = row["jurisdiction"].strip()
            if kind == "text":
                spec = int(row["specificity"] or 1)
                text.append((-spec, i, pattern, jur))
            elif kind == "collection":
                collection[pattern] = jur
    text.sort()
    return [(p, j) for _, _, p, j in text], collection


def load_issuer_aliases(path: Path):
    """Return a list of (pattern_lower, canonical) sorted longest-pattern-first so
    the most specific alias matches first."""
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            pat = row["pattern"].strip().lower()
            canon = row["canonical"].strip()
            if pat:
                rows.append((pat, canon))
    rows.sort(key=lambda r: len(r[0]), reverse=True)
    return rows


def load_doctype_rules(path: Path):
    rules = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            rules.append((-int(row["specificity"] or 1), i, row["pattern"].strip().lower(), row["doc_type"].strip()))
    rules.sort()
    return [(p, d) for _, _, p, d in rules]


# --------------------------------------------------------------------------- #
# Raw value decoding
# --------------------------------------------------------------------------- #


def _decode_raw(value) -> str:
    """Loader stored list-valued raw fields as JSON. Rejoin a JSON list with ';'
    so the first-body rule below applies uniformly to list and string forms."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
        try:
            arr = json.loads(value)
            if isinstance(arr, list):
                return "; ".join(str(x) for x in arr)
        except json.JSONDecodeError:
            pass
    return value if isinstance(value, str) else str(value)


def _collections(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) and value.startswith("["):
        try:
            arr = json.loads(value)
            return [str(x) for x in arr] if isinstance(arr, list) else [value]
        except json.JSONDecodeError:
            return [value]
    return [str(value)]


# --------------------------------------------------------------------------- #
# Date
# --------------------------------------------------------------------------- #


def decade_of(year: int) -> str:
    return f"{(year // 10) * 10}s"


def parse_date(date_raw) -> dict:
    """Parse date_raw without imputation. Returns date_norm/year/decade/dated/
    date_method. dated=1 only for an explicit in-range year."""
    if not date_raw or not str(date_raw).strip():
        return {"date_norm": None, "year": None, "decade": None, "dated": 0, "date_method": "unknown"}
    s = str(date_raw).strip()
    if re.fullmatch(r"\d{1,3}[-?]{1,3}", s):  # 197-, 19-- style partials
        return {"date_norm": s, "year": None, "decade": None, "dated": 0, "date_method": "partial"}
    years = re.findall(r"\d{4}", s)
    if not years:
        return {"date_norm": s, "year": None, "decade": None, "dated": 0, "date_method": "unknown"}
    is_range = bool(re.search(r"\d{4}\s*[-/]\s*\d{4}", s))
    year = min(int(y) for y in years) if is_range else int(years[0])
    method = "range" if is_range else "exact"
    if year == 0 or not (YEAR_MIN <= year <= YEAR_MAX):
        return {"date_norm": s, "year": None, "decade": None, "dated": 0, "date_method": "unknown"}
    return {"date_norm": str(year), "year": year, "decade": decade_of(year), "dated": 1, "date_method": method}


_TITLE_YEAR = re.compile(r"\b(1[89]\d\d|20[0-2]\d)\b")
_FISCAL = re.compile(r"\b(1[89]\d\d|20[0-2]\d)-(\d{2})\b")
_YEAR_ENDING = re.compile(r"year end\w*[^0-9]{0,40}(1[89]\d\d|20[0-2]\d)", re.IGNORECASE)


def recover_title_year(title: Optional[str]) -> Optional[int]:
    """Strict recovery of an explicitly stated year from the title only. Returns
    the year or None. Multiple distinct explicit years -> None (no guessing)."""
    if not title:
        return None
    fm = _FISCAL.search(title)
    if fm and YEAR_MIN <= int(fm.group(1)) <= YEAR_MAX:
        return int(fm.group(1))
    em = _YEAR_ENDING.search(title)
    if em and YEAR_MIN <= int(em.group(1)) <= YEAR_MAX:
        return int(em.group(1))
    distinct = sorted({int(y) for y in _TITLE_YEAR.findall(title) if YEAR_MIN <= int(y) <= YEAR_MAX})
    return distinct[0] if len(distinct) == 1 else None


# --------------------------------------------------------------------------- #
# Jurisdiction
# --------------------------------------------------------------------------- #


def match_text_jurisdiction(text: str, text_rules) -> Optional[str]:
    if not text:
        return None
    tl = text.lower()
    for pattern, jur in text_rules:
        if pattern in tl:
            return jur
    return None


def match_collection_jurisdiction(collections: list[str], coll_rules: dict) -> Optional[str]:
    found = {coll_rules[c] for c in collections if c in coll_rules}
    return next(iter(found)) if len(found) == 1 else None


def classify_jurisdiction(creator: str, publisher: str, collections: list[str], title: str, text_rules, coll_rules) -> tuple[str, str]:
    cj = match_text_jurisdiction(creator, text_rules)
    pj = match_text_jurisdiction(publisher, text_rules)
    strong = [x for x in (cj, pj) if x]
    distinct = set(strong)
    if len(distinct) == 1:
        return strong[0], ("creator" if cj else "publisher")
    if len(distinct) > 1:
        return "unknown", "unknown"  # creator/publisher conflict
    colj = match_collection_jurisdiction(collections, coll_rules)
    if colj:
        return colj, "collection"
    tj = match_text_jurisdiction(title, text_rules)
    if tj:
        return tj, "title"
    return "unknown", "unknown"


# --------------------------------------------------------------------------- #
# Issuer
# --------------------------------------------------------------------------- #


def _smart_title(s: str) -> str:
    out = []
    for i, word in enumerate(s.split(" ")):
        low = word.lower()
        out.append(low if (i > 0 and low in _SMALL) else (word[:1].upper() + word[1:].lower()))
    return " ".join(out)


def clean_issuer(text: str) -> str:
    """Collapse the known IA noise into a bare body name."""
    if not text:
        return ""
    s = text.split(";")[0]            # first body of a ;-joined list
    s = s.split(" = ")[0]             # drop "= Statistique..." bilingual tail
    if " : " in s:                    # "Place : Body" -> Body
        s = s.split(" : ", 1)[1]
    s = s.replace("[", "").replace("]", "")
    s = re.sub(r",?\s*issuing body\.?$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip().strip(",.").strip()
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        s = _smart_title(s)
    return s


def is_anaphoric(s: str) -> bool:
    return bool(_ANAPHORA.match(s.strip())) if s else False


def match_alias(cleaned: str, aliases) -> Optional[str]:
    cl = cleaned.lower()
    for pattern, canon in aliases:
        if pattern in cl:
            return canon
    return None


def normalize_issuer(creator_raw, publisher_raw, aliases) -> tuple[Optional[str], str, Optional[str]]:
    """Return (issuer_norm, method, unmapped_key). method in {alias, unmapped,
    unknown}. Prefer the fuller creator; resolve publisher anaphora to it."""
    cand_creator = clean_issuer(_decode_raw(creator_raw))
    cand_publisher = clean_issuer(_decode_raw(publisher_raw))
    candidates = [c for c in (cand_creator, cand_publisher) if c and not is_anaphoric(c)]
    if not candidates:
        return "unknown", "unknown", None
    cand = candidates[0]
    canon = match_alias(cand, aliases)
    if canon:
        return canon, "alias", None
    return cand, "unmapped", cand


# --------------------------------------------------------------------------- #
# Doc type
# --------------------------------------------------------------------------- #


def classify_doctype(title, creator, doctype_rules) -> tuple[str, str]:
    title = _decode_raw(title)
    creator = _decode_raw(creator)
    if not title and not creator:
        return "unknown", "unknown"
    tl = title.lower()
    cl = creator.lower()
    for pattern, dt in doctype_rules:
        if pattern in tl:
            return dt, "title"
        if pattern in cl:
            return dt, "creator"
    return "other", "default"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


def period_of(year: Optional[int], dated: int) -> str:
    if not dated or year is None:
        return "undated"
    if year < 1960:
        return "pre-1960"
    if year > 2009:
        return "post-2009"
    return decade_of(year)


def normalize_items(conn: sqlite3.Connection, config_dir: Path) -> dict:
    text_rules, coll_rules = load_jurisdiction_rules(config_dir / "jurisdiction_rules.csv")
    aliases = load_issuer_aliases(config_dir / "issuer_aliases.csv")
    doctype_rules = load_doctype_rules(config_dir / "doctype_rules.csv")

    rows = conn.execute(
        "SELECT item_id, title, creator_raw, publisher_raw, date_raw, collection_raw FROM items"
    ).fetchall()
    passages_by_item = dict(conn.execute("SELECT item_id, COUNT(*) FROM passages GROUP BY item_id").fetchall())

    unmapped = Counter()
    stats = {
        "items": len(rows),
        "undated_before_items": 0, "undated_before_passages": 0,
        "recovered_items": 0, "recovered_passages": 0,
        "undated_after_items": 0, "undated_after_passages": 0,
        "jurisdiction": Counter(), "jurisdiction_unknown": 0,
        "issuer_method": Counter(), "doc_type": Counter(),
    }

    for r in rows:
        item_id = r["item_id"]
        npass = passages_by_item.get(item_id, 0)

        d = parse_date(r["date_raw"])
        if not d["dated"]:
            stats["undated_before_items"] += 1
            stats["undated_before_passages"] += npass
            y = recover_title_year(_decode_raw(r["title"]))
            if y is not None:
                d = {"date_norm": str(y), "year": y, "decade": decade_of(y), "dated": 1, "date_method": "title_extracted"}
                stats["recovered_items"] += 1
                stats["recovered_passages"] += npass
            else:
                stats["undated_after_items"] += 1
                stats["undated_after_passages"] += npass

        jur, jmethod = classify_jurisdiction(
            _decode_raw(r["creator_raw"]), _decode_raw(r["publisher_raw"]),
            _collections(r["collection_raw"]), _decode_raw(r["title"]), text_rules, coll_rules,
        )
        stats["jurisdiction"][jur] += 1
        if jur == "unknown":
            stats["jurisdiction_unknown"] += 1

        issuer, imethod, unmapped_key = normalize_issuer(r["creator_raw"], r["publisher_raw"], aliases)
        stats["issuer_method"][imethod] += 1
        if imethod == "unmapped" and unmapped_key:
            unmapped[unmapped_key] += 1

        dtype, dmethod = classify_doctype(r["title"], r["creator_raw"], doctype_rules)
        stats["doc_type"][dtype] += 1

        conn.execute(
            "UPDATE items SET date_norm=?, year=?, decade=?, dated=?, date_method=?, "
            "jurisdiction_norm=?, jurisdiction_method=?, issuer_norm=?, issuer_method=?, "
            "doc_type_norm=?, doc_type_method=? WHERE item_id=?",
            (d["date_norm"], d["year"], d["decade"], d["dated"], d["date_method"],
             jur, jmethod, issuer, imethod, dtype, dmethod, item_id),
        )
    conn.commit()

    stats["jurisdiction"] = dict(stats["jurisdiction"])
    stats["issuer_method"] = dict(stats["issuer_method"])
    stats["doc_type"] = dict(stats["doc_type"])
    stats["_unmapped"] = unmapped
    return stats


def compute_coverage(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM coverage_cells")
    rows = conn.execute(
        "SELECT i.item_id, i.year, i.dated, i.jurisdiction_norm, i.issuer_norm, i.doc_type_norm, "
        "(SELECT COUNT(*) FROM pages p WHERE p.item_id=i.item_id) AS pages, "
        "(SELECT COUNT(*) FROM passages s WHERE s.item_id=i.item_id) AS passages FROM items i"
    ).fetchall()
    agg = defaultdict(lambda: [0, 0, 0, 0])  # items, pages, passages, undated
    for r in rows:
        period = period_of(r["year"], r["dated"])
        key = (period, r["jurisdiction_norm"] or "unknown", r["issuer_norm"] or "unknown", r["doc_type_norm"] or "unknown")
        cell = agg[key]
        cell[0] += 1
        cell[1] += r["pages"]
        cell[2] += r["passages"]
        cell[3] += 1 if period == "undated" else 0
    for cid, (key, vals) in enumerate(sorted(agg.items()), start=1):
        period, jur, issuer, dtype = key
        conn.execute(
            "INSERT INTO coverage_cells (cell_id, period, jurisdiction, issuer, doc_type, "
            "item_count, page_count, passage_count, undated_count, ocr_conf_bucket, ocr_conf_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cid, period, jur, issuer, dtype, vals[0], vals[1], vals[2], vals[3], None, None),
        )
    conn.commit()
    return len(agg)


def write_reports(stats: dict, cells: int, out_dir: Path, conn: sqlite3.Connection) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    unmapped = stats.pop("_unmapped")
    total = stats["items"]
    matrix = defaultdict(lambda: Counter())
    for r in conn.execute("SELECT jurisdiction_norm, decade, dated, year FROM items"):
        matrix[r["jurisdiction_norm"] or "unknown"][period_of(r["year"], r["dated"])] += 1

    report = {
        "items": total,
        "coverage_cells": cells,
        "undated_before_recovery": {"items": stats["undated_before_items"], "passages": stats["undated_before_passages"]},
        "recovered_from_title": {"items": stats["recovered_items"], "passages": stats["recovered_passages"]},
        "undated_after_recovery": {"items": stats["undated_after_items"], "passages": stats["undated_after_passages"]},
        "jurisdiction_distribution": stats["jurisdiction"],
        "jurisdiction_unknown_pct": round(100.0 * stats["jurisdiction_unknown"] / total, 2) if total else 0.0,
        "issuer_method_distribution": stats["issuer_method"],
        "unmapped_issuer_items": sum(unmapped.values()),
        "unmapped_issuer_distinct": len(unmapped),
        "doc_type_distribution": stats["doc_type"],
        "jurisdiction_by_period": {j: dict(sorted(c.items())) for j, c in sorted(matrix.items())},
    }
    (out_dir / "normalize_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    unmapped_dir = out_dir.parent / "unmapped"
    unmapped_dir.mkdir(parents=True, exist_ok=True)
    with (unmapped_dir / "issuer_unmapped.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["count", "cleaned_issuer"])
        for name, n in unmapped.most_common():
            w.writerow([n, name])


def run(config_path: Path, out_dir: Path) -> dict:
    conn = db.init_db(db.resolve_db_path(config_path))
    try:
        stats = normalize_items(conn, config_path.parent)
        cells = compute_coverage(conn)
        write_reports(dict(stats, _unmapped=stats["_unmapped"]), cells, out_dir, conn)
    finally:
        conn.close()
    return {"items": stats["items"], "coverage_cells": cells}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Phase 5 normalization + coverage into civic.db.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default="reports/phase5", type=Path)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run(args.config, args.out)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
