"""Derived dates for undated documents, and their measured accuracy (docs/formats/derived_dates.md).

    python scripts/v2/derive_dates.py --collections pilot microlog --eval-sample 3000 --seed 20261107

For every undated item (items.dated = 0) the date reader (archive_debugger.dates) reads the title and
the first pages and writes reports/v2/dates/<collection>/derived_dates.jsonl: item_id, year, method,
confidence, evidence, leaf, method_version. The catalogue fields are never touched.

Accuracy: on a seeded sample of dated items, the catalogue year is hidden, the reader runs on the same
title and pages, and the derived year is compared with the catalogue year: exact and within one year,
per method and confidence, with Wilson 95% intervals, plus coverage (the share given a date). Written to
reports/v2/dates/accuracy.json and accuracy.md. Reads the corpora read-only; no network."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger import dates, scopes  # noqa: E402
from archive_debugger.audit.calibration import wilson  # noqa: E402
from archive_debugger.audit.records import write_jsonl  # noqa: E402

OUT = REPO / "reports" / "v2" / "dates"


def evaluate(rows: list) -> dict:
    """rows: [(catalogue year, DerivedDate or None)]."""
    out = {"items": len(rows), "dated_by_reader": sum(1 for _, d in rows if d), "by": {}}
    groups = defaultdict(list)
    for year, d in rows:
        if d is None:
            continue
        groups[("all", "all")].append((year, d))
        groups[("method", d.method)].append((year, d))
        groups[("confidence", d.confidence)].append((year, d))
    for (kind, name), members in sorted(groups.items()):
        n = len(members)
        exact = sum(1 for y, d in members if d.year == y)
        near = sum(1 for y, d in members if abs(d.year - y) <= 1)
        out["by"][f"{kind}:{name}"] = {"n": n, "exact": exact, "exact_rate": exact / n, "exact_wilson": wilson(exact, n),
                                       "within_1": near, "within_1_rate": near / n, "within_1_wilson": wilson(near, n)}
    out["coverage"] = out["dated_by_reader"] / out["items"] if out["items"] else None
    return out


def main(argv=None) -> int:
    from archive_debugger.eval.rundb import open_corpus_read_only
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collections", nargs="*", default=["pilot", "microlog"])
    parser.add_argument("--eval-sample", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args(argv)
    report = {"method_version": dates.METHOD_VERSION, "seed": args.seed, "collections": {}}
    for name in args.collections:
        conn = open_corpus_read_only(scopes.resolve_scope(name).db_path)
        undated = conn.execute("SELECT item_id, title FROM items WHERE dated = 0 ORDER BY item_id").fetchall()
        derived = []
        for item_id, title in undated:
            d = dates.read_date(title, dates.first_pages(conn, item_id))
            if d is not None:
                derived.append({"item_id": item_id, **d.to_dict()})
        write_jsonl(OUT / name / "derived_dates.jsonl", derived)
        dated = conn.execute("SELECT item_id, title, year FROM items WHERE dated = 1 AND year IS NOT NULL "
                             "ORDER BY item_id").fetchall()
        sample = random.Random(f"{args.seed}:{name}").sample(dated, min(args.eval_sample, len(dated)))
        rows = [(year, dates.read_date(title, dates.first_pages(conn, item_id))) for item_id, title, year in sample]
        by_conf = defaultdict(int)
        for d in derived:
            by_conf[d["confidence"]] += 1
        report["collections"][name] = {"undated_items": len(undated), "derived": len(derived),
                                       "derived_by_confidence": dict(by_conf), "accuracy_on_dated": evaluate(rows)}
        print(name, "undated", len(undated), "derived", len(derived), dict(by_conf))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "accuracy.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    lines = ["# Derived dates: accuracy with the catalogue date hidden", "",
             f"Reader {dates.METHOD_VERSION}; seed {args.seed}. A derived date is stored apart from the catalogue date "
             "and never replaces it.", ""]
    for name, c in report["collections"].items():
        acc = c["accuracy_on_dated"]
        lines += [f"## {name}", "", f"Undated items: {c['undated_items']}; given a derived date: {c['derived']} "
                  f"({c['derived_by_confidence']}). Evaluation sample of dated items: {acc['items']}, of which the reader "
                  f"dated {acc['dated_by_reader']} (coverage {acc['coverage']:.3f}).", "",
                  "| Group | n | Exact (95%) | Within one year (95%) |", "| --- | ---: | --- | --- |"]
        for key, g in acc["by"].items():
            lines.append(f"| {key} | {g['n']} | {g['exact_rate']:.3f} ({g['exact_wilson'][0]:.3f}-{g['exact_wilson'][1]:.3f}) | "
                         f"{g['within_1_rate']:.3f} ({g['within_1_wilson'][0]:.3f}-{g['within_1_wilson'][1]:.3f}) |")
        lines.append("")
    (OUT / "accuracy.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
