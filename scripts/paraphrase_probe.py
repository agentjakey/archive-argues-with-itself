"""Paraphrase robustness probe (read-only diagnostic). Runs each phrasing of each
question group through the real retrieval + frozen abstention gate with NO model call
(provider stub path), and reports how stable the outcome and the retrieved set are
across phrasings of the same question.

Input: a JSONL of groups (see eval/paraphrase_probe.jsonl), lines starting with # or
blank are ignored. Each group: {group_id, phrasings:[...], filters?:{}, expected?:...}.

Per phrasing it records: abstained (the frozen gate's decision), uncovered_terms,
salient_terms, the top-10 retrieved passage_ids, and n_items in the model window.
Per group it computes outcome agreement (do all phrasings agree answerable vs abstain)
and retrieval overlap (mean pairwise Jaccard of the top-10 id sets), and classifies a
disagreeing group as gate-driven (phrasings retrieve nearly the same passages but the
gate decides differently) or retrieval-driven (phrasings retrieve different passages).

Changes nothing: no rule, no retrieval config, no gold. Uses the shipped config.

    python scripts/paraphrase_probe.py [eval/paraphrase_probe.jsonl]
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

TOPK_REPORT = 10
OVERLAP_HI = 0.7   # >= this mean Jaccard on a split group -> gate-driven


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def load_groups(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(json.loads(s))
    return out


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.generate.answer import coverage_of, is_thin
    from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool
    from archive_debugger.retrieve.search import Retriever

    path = Path(argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else "eval/paraphrase_probe.jsonl"))
    gcfg = load_generate_config("config/pilot.toml")
    groups = load_groups(path)
    retriever = Retriever("config/pilot.toml")   # shipped config; no model is constructed

    rows = []   # per-phrasing records
    summaries = []
    try:
        for g in groups:
            filt = build_filters(g.get("filters"))
            per = []
            for text in g["phrasings"]:
                pool, hits = retrieve_pool(retriever, text, filt, gcfg["top_k"])
                cov = coverage_of(text, hits)
                top = [h["passage_id"] for h in hits[:TOPK_REPORT]]
                rec = {"group": g["group_id"], "phrasing": text,
                       "abstained": is_thin(cov, min_passages=gcfg["min_passages"]),
                       "uncovered_terms": cov.uncovered_terms, "salient_terms": cov.salient_terms,
                       "top10": top, "n_items": cov.n_items}
                per.append(rec)
                rows.append(rec)
            outcomes = {r["abstained"] for r in per}
            unanimous = len(outcomes) == 1
            sets = [set(r["top10"]) for r in per]
            pairs = list(combinations(range(len(sets)), 2))
            overlap = sum(jaccard(sets[i], sets[j]) for i, j in pairs) / len(pairs) if pairs else 1.0
            # Classify a split by mechanism, not by overlap alone: it is gate-driven when
            # the abstaining phrasings each carry an uncovered salient term that the
            # answering phrasings do not (the frozen gate's term rule is what flipped the
            # outcome), and retrieval-driven otherwise (the phrasings genuinely retrieve
            # different evidence and the gate reacted to that). Overlap is reported too,
            # because in this corpus it is low across the board and so does not by itself
            # separate the two cases.
            answering = [r for r in per if not r["abstained"]]
            abstaining = [r for r in per if r["abstained"]]
            gate_explains = bool(abstaining) and bool(answering) and \
                all(r["uncovered_terms"] for r in abstaining) and all(not r["uncovered_terms"] for r in answering)
            kind = "unanimous" if unanimous else ("gate-driven" if gate_explains else "retrieval-driven")
            summaries.append({"group": g["group_id"], "expected": g.get("expected"), "n": len(per),
                              "unanimous": unanimous,
                              "outcome": ("abstain" if all(r["abstained"] for r in per)
                                          else "answer" if not any(r["abstained"] for r in per) else "SPLIT"),
                              "overlap": overlap, "kind": kind,
                              "abstained_flags": [r["abstained"] for r in per]})
    finally:
        retriever.close()

    # per-group table
    print(f"{'group':26} {'exp':11} {'outcome':8} {'overlap':>7}  kind")
    print("-" * 72)
    for s in summaries:
        print(f"{s['group']:26} {str(s['expected']):11} {s['outcome']:8} {s['overlap']:7.2f}  {s['kind']}")

    # per-phrasing detail for split groups
    split = [s for s in summaries if not s["unanimous"]]
    if split:
        print("\nSplit groups, per phrasing (abstained | uncovered_terms | salient_terms):")
        for s in split:
            print(f"\n  {s['group']} (overlap {s['overlap']:.2f}, {s['kind']}):")
            for r in [x for x in rows if x["group"] == s["group"]]:
                print(f"    [{'ABSTAIN' if r['abstained'] else 'answer '}] uncovered={r['uncovered_terms']} "
                      f"salient={r['salient_terms']}")
                print(f"       {r['phrasing']!r}")

    # summary
    n = len(summaries)
    unanimous = [s for s in summaries if s["unanimous"]]
    gate = [s for s in split if s["kind"] == "gate-driven"]
    retr = [s for s in split if s["kind"] == "retrieval-driven"]
    exp_norm = {"answerable": "answer", "abstain": "abstain"}
    mismatch = [s for s in unanimous if s["expected"] and s["outcome"] != exp_norm.get(s["expected"], s["expected"])]
    print("\n" + "=" * 72)
    print(f"groups: {n} | unanimous: {len(unanimous)} | split: {len(split)} "
          f"(gate-driven {len(gate)}, retrieval-driven {len(retr)})")
    print(f"mean top-10 overlap across all groups: {sum(s['overlap'] for s in summaries)/n:.2f}")
    if split:
        print("split groups: " + ", ".join(f"{s['group']}({s['kind']})" for s in split))
    if mismatch:
        print("unanimous but not the expected outcome: "
              + ", ".join(f"{s['group']} got {s['outcome']}, expected {s['expected']}" for s in mismatch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
