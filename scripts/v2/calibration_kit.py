"""Build the calibration kit (docs/formats/audit.md): judge items for a person to label blind,
grouped by answer, in batches of about 50 sentences.

Two units. Every answer in the collections is in the kit as one answer item, labelled once on
ANSWERS. A stratified sample of sentence items is labelled on SUPPORTS and IN SCOPE. Strata:
collection x the v1 author decision on SUPPORTS (pass, partial, fail) x whether a gate flagged the
sentence. Always included: every sentence whose v1 decision was not "pass", every sentence a gate
flagged, and every sentence of the answers named with --include-answers (for example answers the v1
audit recorded as out of scope).

The kit is ordered by answer: an answer item, then its sampled sentences. Answers come in the order
of their first sentence in the stratified order, so every stretch of the kit spreads over the
strata, except that answers holding an always-included sentence are interleaved with the rest so
that all of them fall within about the first 120 sentences (the first three batches). A batch never splits an answer. The person never sees the
v1 decision, a gate flag, or a judge's verdict while labelling.

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

BATCH_SENTENCES = 50
KIT_FORMAT = 2


def order_by_answer(sentence_order: list, answer_items: list, must: frozenset = frozenset(),
                    must_by: int = 120) -> list:
    """Answer item first, then its sentences in sentence order. Answers come in the order of their
    first sentence in sentence_order, answers with no sampled sentence last; answers holding a
    sentence in `must` are interleaved with the rest in proportion to their sentences, so all of
    them are placed within about the first `must_by` sentences."""
    first_seen: dict = {}
    by_answer: dict = {}
    for position, it in enumerate(sentence_order):
        key = (it["collection"], it["qid"])
        first_seen.setdefault(key, position)
        by_answer.setdefault(key, []).append(it)
    answers = {(a["collection"], a["qid"]): a for a in answer_items}
    keys = sorted(answers, key=lambda k: (first_seen.get(k, len(sentence_order)), k))
    promoted = [k for k in keys if any(it["item_id"] in must for it in by_answer.get(k, []))]
    others = [k for k in keys if k not in set(promoted)]
    share = min(1.0, sum(len(by_answer[k]) for k in promoted) / max(1, must_by))
    order, placed_promoted, placed = [], 0, 0
    while promoted or others:
        if promoted and (not others or placed_promoted <= share * placed):
            key = promoted.pop(0)
            placed_promoted += len(by_answer[key])
        else:
            key = others.pop(0)
        placed += len(by_answer.get(key, []))
        order.append(key)
    out = []
    for key in order:
        out.append(answers[key])
        out.extend(sorted(by_answer.get(key, []), key=lambda it: it["sentence_no"]))
    return out


def assign_batches(rows: list, batch_sentences: int = BATCH_SENTENCES) -> None:
    """kit_batch on every row: a batch closes after the answer that brings it to batch_sentences
    sentences, so no answer is split."""
    batch, count = 1, 0
    for n, row in enumerate(rows):
        if row["kind"] == "answer" and count >= batch_sentences:
            batch, count = batch + 1, 0
        row["kit_batch"] = batch
        row["kit_position"] = n + 1
        if row["kind"] == "sentence":
            count += 1


def main(argv=None) -> int:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", type=int, default=300, help="sentence items")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--collections", nargs="*", default=None)
    parser.add_argument("--include-answers", nargs="*", default=[], help="collection:qid, every sentence included")
    parser.add_argument("--out", type=Path, default=AUDIT_DIR / "calibration")
    args = parser.parse_args(argv)

    names = args.collections or collections.all_names()
    items, labels = build_items(names)
    sentences = [it for it in items if it["kind"] == "sentence"]
    answer_items = [it for it in items if it["kind"] == "answer"]
    flagged = set()
    for name in names:
        conn = corpus_connection(collections.load(name))
        for it in sentences:
            if it["collection"] == name and gates.run_gates(conn, it)["flags"]:
                flagged.add(it["item_id"])
    wanted_answers = {tuple(a.split(":", 1)) for a in args.include_answers}
    must = {it["item_id"] for it in sentences
            if labels.get(it["item_id"]) not in (None, "pass") or it["item_id"] in flagged
            or (it["collection"], it["qid"]) in wanted_answers}

    def stratum(it):
        return (it["collection"], labels.get(it["item_id"], "unlabeled"), it["item_id"] in flagged)

    sample = calibration.stratified_sample(sentences, stratum, args.size, args.seed, must_include=must)
    kit = [dict(it) for it in order_by_answer(sample, answer_items, frozenset(must))]
    assign_batches(kit)
    version = hashlib.sha256(("kit2\n" + "\n".join(r["item_id"] for r in kit)).encode("utf-8")).hexdigest()[:12]
    for row in kit:
        row["kit_version"] = version
        row["kit_format"] = KIT_FORMAT
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "kit.jsonl", kit)

    kit_sentences = [r for r in kit if r["kind"] == "sentence"]
    first_150, seen = [], 0
    for r in kit:
        if r["kind"] == "sentence":
            if seen == 150:
                break
            first_150.append(r)
            seen += 1

    def strata(rows):
        return {f"{c}|v1={l}|flagged={f}": n for (c, l, f), n in sorted(Counter(stratum(r) for r in rows).items())}

    manifest = {
        "kit_version": version, "kit_format": KIT_FORMAT, "seed": args.seed,
        "sentence_items": len(kit_sentences), "answer_items": len(kit) - len(kit_sentences),
        "batch_sentences": BATCH_SENTENCES, "batches": kit[-1]["kit_batch"] if kit else 0,
        "batch_sizes": {str(b): {"sentences": sum(1 for r in kit_sentences if r["kit_batch"] == b),
                                 "answers": sum(1 for r in kit if r["kind"] == "answer" and r["kit_batch"] == b)}
                        for b in sorted({r["kit_batch"] for r in kit})},
        "collections": names, "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "must_include": {"v1_not_pass": sum(1 for i in must if labels.get(i) not in (None, "pass")),
                         "gate_flagged": len(flagged), "answers": sorted(args.include_answers), "total": len(must)},
        "must_include_in_first_150_sentences": sum(1 for r in first_150 if r["item_id"] in must),
        "strata": strata(kit_sentences), "first_150_strata": strata(first_150), "population": strata(sentences),
    }
    (args.out / "kit.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("kit_version", "sentence_items", "answer_items", "batches",
                                               "batch_sizes", "must_include", "must_include_in_first_150_sentences")},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
