"""Scope-local microlog jurisdiction remap (additive).

The shared Phase-5 normalizer (ingest.normalize) resolves only federal/Ontario/Alberta/
international from config/jurisdiction_rules.csv, leaving ~43% of microlog items unknown.
This module adds a microlog-ONLY rule set (config/microlog_jurisdiction_rules.csv) and
re-resolves the microlog scope's items that are currently 'unknown', writing the improved
jurisdiction back into civic_microlog.db ONLY. It never touches the shared rules file,
ingest.normalize, config/pilot.toml, or the pilot databases.

Contract, matching the standing scope-build rules:
  - Structured issuer metadata only (creator/publisher/collection). Title and passage text
    are never read here, so a province named in a document's subject cannot be mistaken for
    its issuer.
  - Precision over recall. A jurisdiction is chosen only when creator OR publisher yields
    exactly one jurisdiction; a creator/publisher conflict, or no match, stays unknown.
  - Every resolution is proxy-derived and marked jurisdiction_method='microlog_map:<field>',
    so it is never shown as recorded metadata. Each firing rule is logged for audit.
  - Idempotent: a re-run first reverts prior microlog_map resolutions, so the reported
    before/after is always measured against the shared-normalizer baseline.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Optional

from archive_debugger import scopes
from archive_debugger.ingest import db, normalize

SHARED_RULES = Path("config/jurisdiction_rules.csv")
MICROLOG_RULES = Path("config/microlog_jurisdiction_rules.csv")
METHOD_PREFIX = "microlog_map:"


def _norm(s: Optional[str]) -> str:
    """Lowercase and strip accents, so ASCII rule patterns match accented issuers
    (e.g. 'Quebec' matches 'Quebec')."""
    decomposed = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def load_rules(paths) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Merge one or more jurisdiction-rule CSVs into a single specificity-sorted text-rule
    list and a collection map. Same CSV format as config/jurisdiction_rules.csv. Comment
    lines (starting with '#') and blank rows are ignored."""
    text: list[tuple[int, int, str, str]] = []
    collection: dict[str, str] = {}
    order = 0
    for path in paths:
        with Path(path).open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                kind = (row.get("kind") or "").strip()
                if not kind or kind.startswith("#"):
                    continue
                pattern = (row.get("pattern") or "").strip().lower()
                jur = (row.get("jurisdiction") or "").strip()
                if not pattern or not jur:
                    continue
                if kind == "text":
                    text.append((-int(row.get("specificity") or 1), order, pattern, jur))
                    order += 1
                elif kind == "collection":
                    collection[pattern] = jur
    text.sort()
    return [(p, j) for _, _, p, j in text], collection


# Cataloguer jurisdiction tags like "(Sask.)": a deliberate parenthetical jurisdiction call,
# treated as authoritative even when the field also names Canada.
_ABBREV_TAGS = {
    "(b.c.)", "(man.)", "(sask.)", "(n.s.)", "(n.b.)", "(que.)", "(qc)", "(n.l.)",
    "(nfld.)", "(p.e.i.)", "(y.t.)", "(n.w.t.)", "(nun.)", "(ont.)",
}


def _field(text: str, text_rules) -> tuple[Optional[str], Optional[str]]:
    """One issuer field's jurisdiction, precision-first. All substring hits are collected.
    A cataloguer '(prov.)' tag is authoritative. Otherwise the hits must name exactly one
    jurisdiction; a province together with a federal signal ('canada' or a named federal
    agency), or two different provinces, is ambiguous and yields NO jurisdiction. This is
    what stops a federal body named for its provincial region (e.g. 'Forestry Canada,
    Newfoundland and Labrador Region') from being mislabeled as that province."""
    tl = _norm(text)
    if not tl:
        return None, None
    hits = [(p, j) for p, j in text_rules if p in tl]
    if not hits:
        return None, None
    for p, j in hits:
        if p in _ABBREV_TAGS:
            return j, p
    jurs = {j for _, j in hits}
    if len(jurs) == 1:
        return hits[0][1], hits[0][0]   # hits are specificity-ordered; the strongest pattern
    return None, "ambiguous"


def resolve(creator: str, publisher: str, collections, text_rules, coll_rules) -> tuple[str, str, Optional[str]]:
    """(jurisdiction, method, pattern). Issuer metadata only, no title. creator/publisher
    conflict, an ambiguous field, or no match -> ('unknown', 'conflict'|'none', None)."""
    cj, cp = _field(creator, text_rules)
    pj, pp = _field(publisher, text_rules)
    strong = [(j, p, f) for j, p, f in ((cj, cp, "creator"), (pj, pp, "publisher")) if j]
    distinct = {j for j, _, _ in strong}
    if len(distinct) == 1:
        j, p, f = strong[0]
        return j, f, p
    if len(distinct) > 1:
        return "unknown", "conflict", None
    found = {coll_rules[c] for c in collections if c in coll_rules}
    if len(found) == 1:
        return next(iter(found)), "collection", "collection"
    return "unknown", "none", None


def _distribution(conn: sqlite3.Connection) -> dict:
    return {j: n for j, n in conn.execute(
        "SELECT COALESCE(jurisdiction_norm, 'unknown') j, COUNT(*) c FROM items GROUP BY j")}


def apply_resolver(conn: sqlite3.Connection, text_rules, coll_rules, *, dry_run: bool = False,
                   sample_per_jur: int = 5) -> dict:
    """Re-resolve currently-unknown microlog items and write the result back. Returns an
    auditable report: baseline/after distributions, per-rule firing counts, conflicts, and a
    small per-jurisdiction sample (issuer/title metadata) for the precision spot-check."""
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    # Revert any prior scope-local resolution so before/after is always vs the shared baseline.
    if not dry_run:
        conn.execute("UPDATE items SET jurisdiction_norm='unknown', jurisdiction_method='unknown' "
                     "WHERE jurisdiction_method LIKE ?", (METHOD_PREFIX + "%",))
        conn.commit()
    baseline = _distribution(conn)
    baseline_unknown = baseline.get("unknown", 0)

    rows = conn.execute(
        "SELECT item_id, title, creator_raw, publisher_raw, collection_raw FROM items "
        "WHERE jurisdiction_norm = 'unknown' OR jurisdiction_norm IS NULL"
    ).fetchall()

    per_rule: Counter = Counter()      # (pattern, jurisdiction) -> count
    per_jur: Counter = Counter()       # jurisdiction -> resolved count
    conflicts = 0
    updates: list[tuple[str, str, str]] = []
    samples: dict[str, list[dict]] = {}
    for r in rows:
        creator = normalize._decode_raw(r["creator_raw"])
        publisher = normalize._decode_raw(r["publisher_raw"])
        colls = normalize._collections(r["collection_raw"])
        jur, method, pattern = resolve(creator, publisher, colls, text_rules, coll_rules)
        if jur == "unknown":
            if method == "conflict":
                conflicts += 1
            continue
        per_rule[(pattern, jur)] += 1
        per_jur[jur] += 1
        updates.append((jur, METHOD_PREFIX + method, r["item_id"]))
        bucket = samples.setdefault(jur, [])
        if len(bucket) < sample_per_jur:
            bucket.append({
                "item_id": r["item_id"],
                "pattern": pattern,
                "field": method,
                "creator": creator[:120],
                "publisher": publisher[:120],
                "title": normalize._decode_raw(r["title"])[:120],
            })

    if not dry_run:
        conn.executemany(
            "UPDATE items SET jurisdiction_norm=?, jurisdiction_method=? WHERE item_id=?", updates)
        conn.commit()
        normalize.compute_coverage(conn)   # refresh coverage_cells from the updated items (no re-derivation)

    after = _distribution(conn) if not dry_run else dict(baseline)
    if dry_run:
        after = dict(baseline)
        for jur, n in per_jur.items():
            after[jur] = after.get(jur, 0) + n
        after["unknown"] = baseline_unknown - sum(per_jur.values())

    after_unknown = after.get("unknown", 0)
    resolved = sum(per_jur.values())
    deltas = {j: after.get(j, 0) - baseline.get(j, 0) for j in sorted(set(baseline) | set(after))}
    return {
        "items": total,
        "baseline_unknown": baseline_unknown,
        "baseline_unknown_pct": round(100.0 * baseline_unknown / total, 2) if total else 0.0,
        "after_unknown": after_unknown,
        "after_unknown_pct": round(100.0 * after_unknown / total, 2) if total else 0.0,
        "resolved": resolved,
        "conflicts_left_unknown": conflicts,
        "baseline_distribution": dict(sorted(baseline.items())),
        "after_distribution": dict(sorted(after.items())),
        "deltas": deltas,
        "per_rule": {f"{pat} -> {jur}": n for (pat, jur), n in per_rule.most_common()},
        "samples": samples,
        "dry_run": dry_run,
    }


def run(scope_name: str = "microlog", *, dry_run: bool = False,
        rule_paths=(SHARED_RULES, MICROLOG_RULES), out_dir: Optional[Path] = None) -> dict:
    scope = scopes.resolve_scope(scope_name)
    if scope.inherit:
        raise scopes.ScopeError(
            f"refusing to remap the inherit/default scope {scope_name!r}; this is microlog-only")
    text_rules, coll_rules = load_rules(rule_paths)
    with scopes.activate(scope):
        conn = db.connect(scope.db_path)   # fenced to the microlog databases
        try:
            report = apply_resolver(conn, text_rules, coll_rules, dry_run=dry_run)
        finally:
            conn.close()
    out = out_dir or (scope.reports_dir / "jurisdiction")
    out.mkdir(parents=True, exist_ok=True)
    (out / "remap_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["_report_path"] = str(out / "remap_report.json")
    return report


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Scope-local microlog issuer->jurisdiction remap (additive).")
    p.add_argument("--scope", default="microlog", help="scope to remap (must not be the pilot/default)")
    p.add_argument("--dry-run", action="store_true", help="report only; do not write civic_microlog.db")
    args = p.parse_args(argv)
    rep = run(args.scope, dry_run=args.dry_run)
    print(f"items={rep['items']} unknown {rep['baseline_unknown']} ({rep['baseline_unknown_pct']}%) "
          f"-> {rep['after_unknown']} ({rep['after_unknown_pct']}%); resolved={rep['resolved']} "
          f"conflicts_left_unknown={rep['conflicts_left_unknown']} dry_run={rep['dry_run']}")
    print("per-rule:", json.dumps(rep["per_rule"], ensure_ascii=False))
    print("deltas:", json.dumps(rep["deltas"], ensure_ascii=False))
    print("report:", rep["_report_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
