"""Calibration: how far a judge (or the panel) can be trusted on one check, measured against
people's labels (docs/formats/audit.md), and the bar a check must clear before it can
be called AI-AUDITED.

The bar (Phase 2 amendment 1, recall rule set at Gate 2a), on the panel's final verdict, per check:
  - Cohen's kappa (pass against not pass) at least KAPPA_MIN, except where one class is under
    SKEW_SHARE of the labels, when kappa means little and the recall rule below decides alone;
  - recall on the not-pass class (partial, fail, unclear: the items the person would not pass) at
    least RECALL_MIN, with its Wilson interval reported; with fewer than RECALL_MIN_LABELS not-pass
    labels no recall claim is made and the check stays human-reviewed;
  - the upper 95% Wilson bound on the false-pass rate at most FALSE_PASS_MAX: of the items the
    panel passed, the share the person would not pass;
  - the upper 95% Wilson bound on overall error at most ERROR_MAX.
A check that misses the bar stays human-reviewed. Items the panel left to the human queue have no
verdict and are reported, not counted as agreement."""
from __future__ import annotations

import math
import random
from collections import Counter
from typing import Optional

KAPPA_MIN = 0.6
FALSE_PASS_MAX = 0.10
ERROR_MAX = 0.15
SKEW_SHARE = 0.10
RECALL_MIN = 0.80
RECALL_MIN_LABELS = 20
Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple:
    """The Wilson score interval for a proportion, as (low, high); (0, 1) when n is 0."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohen_kappa(pairs: list) -> Optional[float]:
    """Cohen's kappa over (rater_a, rater_b) label pairs. None when there are no pairs or the
    chance agreement is 1 (both raters used one and the same class throughout)."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def binary(label: Optional[str]) -> Optional[str]:
    """pass, or not_pass for partial, fail and unclear."""
    if label is None:
        return None
    return "pass" if label == "pass" else "not_pass"


def compare(human: dict, machine: dict, *, recall_min: float = RECALL_MIN) -> dict:
    """Agreement between a person's labels and a judge's (or the panel's) verdicts on one check.
    human and machine map item_id to a class; machine None means no verdict (the human queue)."""
    shared = sorted(i for i in human if i in machine)
    decided = [i for i in shared if machine[i] is not None]
    pairs = [(human[i], machine[i]) for i in decided]
    pairs_bin = [(binary(h), binary(m)) for h, m in pairs]
    n = len(pairs)
    errors = sum(1 for h, m in pairs_bin if h != m)
    passed = [(h, m) for h, m in pairs_bin if m == "pass"]
    false_pass = sum(1 for h, _ in passed if h != "pass")
    human_not_pass = [(h, m) for h, m in pairs_bin if h == "not_pass"]
    missed = sum(1 for _, m in human_not_pass if m == "pass")
    classes = sorted({h for h, _ in pairs})
    recall = {}
    for c in classes:
        support = [m for h, m in pairs if h == c]
        hits = sum(1 for m in support if m == c)
        recall[c] = {"hits": hits, "n": len(support), "recall": hits / len(support) if support else None,
                     "wilson": wilson(hits, len(support))}
    counts = Counter(h for h, _ in pairs_bin)
    minority_share = min(counts.values()) / n if n and len(counts) == 2 else (0.0 if n else None)
    skewed = minority_share is not None and minority_share < SKEW_SHARE
    kappa = cohen_kappa(pairs_bin)
    out = {
        "items_labeled": len(shared), "items_decided": n, "items_to_human": len(shared) - n,
        "confusion": dict(Counter(f"{h}->{m}" for h, m in pairs)),
        "exact_agreement": sum(1 for h, m in pairs if h == m) / n if n else None,
        "kappa_binary": kappa,
        "kappa_classes": cohen_kappa(pairs),
        "error_rate": errors / n if n else None, "error_wilson": wilson(errors, n),
        "false_pass": {"count": false_pass, "of_machine_passes": len(passed),
                       "rate": false_pass / len(passed) if passed else None, "wilson": wilson(false_pass, len(passed))},
        "missed_failures": {"count": missed, "of_human_not_pass": len(human_not_pass),
                            "rate": missed / len(human_not_pass) if human_not_pass else None,
                            "wilson": wilson(missed, len(human_not_pass))},
        "recall": recall, "minority_share": minority_share, "skewed": skewed,
        "not_pass_recall": {"hits": len(human_not_pass) - missed, "n": len(human_not_pass),
                            "recall": (len(human_not_pass) - missed) / len(human_not_pass) if human_not_pass else None,
                            "wilson": wilson(len(human_not_pass) - missed, len(human_not_pass))},
    }
    out["bar"] = bar(out, recall_min=recall_min)
    return out


def bar(m: dict, *, recall_min: float = RECALL_MIN) -> dict:
    reasons = []
    if not m["items_decided"]:
        return {"meets": False, "reasons": ["no labeled items with a verdict"]}
    if not m["skewed"] and (m["kappa_binary"] is None or m["kappa_binary"] < KAPPA_MIN):
        reasons.append(f"kappa {m['kappa_binary']} under {KAPPA_MIN}")
    r = m["not_pass_recall"]
    if r["n"] < RECALL_MIN_LABELS:
        reasons.append(f"only {r['n']} not-pass labels, under {RECALL_MIN_LABELS}: no recall claim")
    elif r["recall"] < recall_min:
        reasons.append(f"not-pass recall {r['recall']:.3f} under {recall_min}")
    if m["false_pass"]["wilson"][1] > FALSE_PASS_MAX:
        reasons.append(f"false-pass upper bound {m['false_pass']['wilson'][1]:.3f} over {FALSE_PASS_MAX}")
    if m["error_wilson"][1] > ERROR_MAX:
        reasons.append(f"error upper bound {m['error_wilson'][1]:.3f} over {ERROR_MAX}")
    return {"meets": not reasons, "reasons": reasons}


def stratified_sample(items: list, strata_of, size: int, seed: int, *, must_include: Optional[set] = None) -> list:
    """size items: every item in must_include first, then the rest drawn from each stratum in
    proportion to its size (at least one from each stratum while room remains), in a seeded order
    that spreads the strata evenly, so any prefix of the result (a batch of 50, the first 150) is
    itself a spread sample."""
    rng = random.Random(seed)
    must_include = must_include or set()
    chosen = [it for it in items if it["item_id"] in must_include]
    rest = [it for it in items if it["item_id"] not in must_include]
    strata: dict = {}
    for it in rest:
        strata.setdefault(strata_of(it), []).append(it)
    for members in strata.values():
        rng.shuffle(members)
    room = max(0, size - len(chosen))
    total = len(rest) or 1
    quota = {k: max(1, round(room * len(v) / total)) for k, v in strata.items()}
    while sum(quota.values()) > room and any(q > 1 for q in quota.values()):
        biggest = max(quota, key=lambda k: quota[k])
        quota[biggest] -= 1
    picked = []
    for k in sorted(strata, key=str):
        picked.extend(strata[k][:quota[k]])
    picked = picked[:room]
    sample = chosen + picked
    # Interleave: round-robin over strata so each stretch of the order mixes them.
    by_stratum: dict = {}
    for it in sample:
        by_stratum.setdefault(strata_of(it), []).append(it)
    for members in by_stratum.values():
        rng.shuffle(members)
    order = []
    keys = sorted(by_stratum, key=str)
    rng.shuffle(keys)
    while any(by_stratum.values()):
        for k in keys:
            if by_stratum[k]:
                order.append(by_stratum[k].pop())
    return order


def spot_check_sample(item_ids: list, size: int, seed: str) -> list:
    """A fresh random sample of AI-judged items for a person to review on a release (50 by
    default); seeded by the release id, so the sample is reproducible and differs per release."""
    rng = random.Random(f"spot-check:{seed}")
    ids = sorted(set(item_ids))
    return sorted(rng.sample(ids, min(size, len(ids))))
