"""Build the calibration kit (docs/formats/audit.md): a stratified sample of judge items
for a person to label blind, in batches of 50, in an order where every batch (and the first 150)
spreads over the strata.

Strata: collection x the v1 author decision on SUPPORTS (pass, partial, fail) x whether a gate
flagged the item. Always included: every item whose v1 decision was not "pass", every item a gate
flagged, and every sentence of the answers named with --include-answers (for example answers the v1
audit recorded as out of scope). The person never sees the v1 decision, a gate flag, or a judge's
verdict while labelling.

    python scripts/v2/calibration_kit.py --size 300 --seed 20261101 \\
        --include-answers microlog:mq43 microlog:mq44
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import calibration, collections, gates  # noqa: E402
from archive_debugger.audit.records import write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, build_items, corpus_connection  # noqa: E402

BATCH_SIZE = 50


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--collections", nargs="*", default=None)
    parser.add_argument("--include-answers", nargs="*", default=[], help="collection:qid, every sentence included")
    parser.add_argument("--out", type=Path, default=AUDIT_DIR / "calibration")
    args = parser.parse_args(argv)

    names = args.collections or collections.all_names()
    items, labels = build_items(names)
    flagged = set()
    for name in names:
        c = collections.load(name)
        conn = corpus_connection(c)
        for it in items:
            if it["collection"] == name and gates.run_gates(conn, it)["flags"]:
                flagged.add(it["item_id"])
    wanted_answers = {tuple(a.split(":", 1)) for a in args.include_answers}
    must = {it["item_id"] for it in items
            if labels.get(it["item_id"]) not in (None, "pass") or it["item_id"] in flagged
            or (it["collection"], it["qid"]) in wanted_answers}

    def stratum(it):
        return (it["collection"], labels.get(it["item_id"], "unlabeled"), it["item_id"] in flagged)

    sample = calibration.stratified_sample(items, stratum, args.size, args.seed, must_include=must)
    kit = []
    for position, it in enumerate(sample):
        row = dict(it)
        row["kit_position"] = position + 1
        row["kit_batch"] = position // BATCH_SIZE + 1
        kit.append(row)
    version = hashlib.sha256("\n".join(r["item_id"] for r in kit).encode("utf-8")).hexdigest()[:12]
    for row in kit:
        row["kit_version"] = version
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "kit.jsonl", kit)
    manifest = {
        "kit_version": version, "seed": args.seed, "size": len(kit), "batch_size": BATCH_SIZE,
        "batches": (len(kit) + BATCH_SIZE - 1) // BATCH_SIZE, "collections": names,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "must_include": {"v1_not_pass": sum(1 for i in must if labels.get(i) not in (None, "pass")),
                         "gate_flagged": len(flagged), "answers": sorted(args.include_answers), "total": len(must)},
        "strata": {f"{c}|v1={l}|flagged={f}": n for (c, l, f), n in sorted(Counter(stratum(r) for r in kit).items())},
        "first_150_strata": {f"{c}|v1={l}|flagged={f}": n
                             for (c, l, f), n in sorted(Counter(stratum(r) for r in kit[:150]).items())},
        "population": {f"{c}|v1={l}|flagged={f}": n for (c, l, f), n in sorted(Counter(stratum(r) for r in items).items())},
    }
    (args.out / "kit.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("kit_version", "size", "batches", "must_include")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
