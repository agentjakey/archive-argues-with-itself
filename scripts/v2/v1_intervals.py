"""v1 sentence-support results with intervals that respect clustering (Phase 2 Part A).

    python scripts/v2/v1_intervals.py --resamples 10000 --seed 20261101

The v1 audit reported strict and lenient sentence support with Wilson intervals, which treat every
sentence as independent. Sentences of one answer share a question, a retrieval and a model call, so
they are not. This script recomputes both rates from the author's v1 decisions and adds a cluster
bootstrap that resamples whole answers, plus the design effect (how much clustering widens the
interval). Reads committed v1 files only; writes reports/v2/baseline/v1_intervals.json.

Denominators: "all kept sentences" is every judged sentence; "answerable" drops the sentences of
answers to questions the v1 gold marks should-abstain (the v1 headline for the pilot used this
denominator; the off-target answers are listed in the v1 audit numbers)."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import collections, items  # noqa: E402
from archive_debugger.audit.calibration import wilson  # noqa: E402

OUT = REPO / "reports" / "v2" / "baseline" / "v1_intervals.json"
V1_NUMBERS = {"pilot": REPO / "reports" / "phase16" / "audit_numbers.json",
              "microlog": REPO / "reports" / "microlog" / "audit_numbers.json"}


def off_target_qids(name: str) -> set:
    path = V1_NUMBERS.get(name)
    if not path or not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    qids = set((data.get("off_target_answers") or {}).get("qids") or [])
    qids |= set(((data.get("pending_author_gold_and_judgments") or {}).get("abstention") or {}).get("false_answer_qids") or [])
    return qids


def cluster_bootstrap(clusters: list, resamples: int, seed: int) -> tuple:
    """95% percentile interval of the pooled rate, resampling whole clusters. clusters: list of
    (successes, n)."""
    rng = random.Random(seed)
    k = len(clusters)
    rates = []
    for _ in range(resamples):
        s = n = 0
        for _ in range(k):
            cs, cn = clusters[rng.randrange(k)]
            s += cs
            n += cn
        rates.append(s / n if n else 0.0)
    rates.sort()
    return rates[int(0.025 * resamples)], rates[min(resamples - 1, int(0.975 * resamples))]


def rate_block(labels_by_answer: dict, passing: set, resamples: int, seed: int) -> dict:
    clusters = [(sum(1 for v in labs if v in passing), len(labs)) for labs in labels_by_answer.values() if labs]
    s = sum(c for c, _ in clusters)
    n = sum(m for _, m in clusters)
    lo, hi = cluster_bootstrap(clusters, resamples, seed)
    wl, wh = wilson(s, n)
    width_w, width_c = wh - wl, hi - lo
    return {"successes": s, "sentences": n, "answers": len(clusters), "rate": round(s / n, 4) if n else None,
            "wilson95": [round(wl, 4), round(wh, 4)], "cluster_bootstrap95": [round(lo, 4), round(hi, 4)],
            "design_effect": round((width_c / width_w) ** 2, 2) if width_w else None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args(argv)
    out = {"resamples": args.resamples, "seed": args.seed, "collections": {}}
    pooled_all: dict = {}
    for name in collections.all_names():
        labels = items.v1_labels(collections.load(name))
        by_answer: dict = {}
        for item_id, label in labels.items():
            _, qid, _ = item_id.split(":")
            by_answer.setdefault(qid, []).append(label)
        excluded = off_target_qids(name)
        answerable = {q: v for q, v in by_answer.items() if q not in excluded}
        out["collections"][name] = {
            "off_target_answers_excluded_for_answerable": sorted(excluded & set(by_answer)),
            "all_kept_sentences": {"strict": rate_block(by_answer, {"pass"}, args.resamples, args.seed),
                                   "lenient": rate_block(by_answer, {"pass", "partial"}, args.resamples, args.seed)},
            "answerable": {"strict": rate_block(answerable, {"pass"}, args.resamples, args.seed),
                           "lenient": rate_block(answerable, {"pass", "partial"}, args.resamples, args.seed)},
        }
        pooled_all.update({f"{name}:{q}": v for q, v in by_answer.items()})
    out["both_collections_all_kept"] = {"strict": rate_block(pooled_all, {"pass"}, args.resamples, args.seed),
                                        "lenient": rate_block(pooled_all, {"pass", "partial"}, args.resamples, args.seed)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
