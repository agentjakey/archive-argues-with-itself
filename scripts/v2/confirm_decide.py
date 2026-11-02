"""The confirm-1 decision pieces registered on 2026-11-02 (docs/evaluation/confirm1_preregistration.md, Amendment).

    python scripts/v2/confirm_decide.py sample
    python scripts/v2/confirm_decide.py guardrail --audit judge-c1g-v1 judge-c1g-v2
    python scripts/v2/confirm_decide.py pooled

sample: the guardrail sample. A fixed random order of all confirm-1 item ids (seed "confirm1-guardrail:20261113"),
and the first 100 questions in that order that both pipelines answered (not refused, no error). Writes each run's
judge items for those questions to reports/v2/benchmark/confirm1/guardrail/<run id>.judge_items.jsonl, for the
audit runs.

guardrail: strict SUPPORTS (sentences passing) and ANSWERS failures (answers not passing) per pipeline on the
sample, from the audit runs' panel finals with the adjudicated finals filling the empty ones
(runs/<audit>/adjudicated.jsonl), and the candidate-minus-v1 difference with a paired bootstrap over the
sampled questions (2,000 resamples, seed 20261105). It fails only if the candidate is shown worse by more than 2
points: SUPPORTS upper bound below -0.02, or ANSWERS-failure lower bound above +0.02.

pooled: the fallback. False refusals (answerable questions refused), candidate minus v1, pooled over the frozen
test and confirm-1 by a stratified paired bootstrap: questions resampled with replacement within each set, the
pooled rate being total refusals over total answerable questions of both sets. 2,000 resamples, seed 20261105.
Passes when the upper 95% bound is at most +0.02."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit.records import read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR  # noqa: E402

BENCH = REPO / "reports" / "v2" / "benchmark"
CONFIRM = BENCH / "confirm1"
V1, CAND = "confirm1-v1", "confirm1-v2-glm53-low-dw0"
TEST_V1, TEST_CAND = "test-v1", "test-v2-glm53-low-dw0"
SAMPLE_SEED = "confirm1-guardrail:20261113"
SAMPLE_SIZE = 100
RESAMPLES, BOOT_SEED, MARGIN = 2000, 20261105, 0.02


def answers(root: Path, run_id: str) -> dict:
    return {r["item_id"]: r for r in read_jsonl(root / "runs" / run_id / "answers.jsonl")}


def ok(row: dict) -> bool:
    return row.get("error") is None and row.get("state") is not None


def answered(row: dict) -> bool:
    return ok(row) and not row.get("refused")


def sample_ids(a: dict, b: dict) -> list:
    order = sorted(set(a) | set(b))
    random.Random(SAMPLE_SEED).shuffle(order)
    picked = [i for i in order if i in a and i in b and answered(a[i]) and answered(b[i])]
    return picked[:SAMPLE_SIZE]


def bench_id(judge_item: dict) -> str:
    return judge_item["qid"].split("/", 1)[1]


def cmd_sample(args) -> int:
    a, b = answers(CONFIRM, V1), answers(CONFIRM, CAND)
    ids = sample_ids(a, b)
    if len(ids) < SAMPLE_SIZE:
        raise SystemExit(f"only {len(ids)} questions answered by both")
    out = CONFIRM / "guardrail"
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(ids)
    for run in (V1, CAND):
        items = [it for it in read_jsonl(CONFIRM / "runs" / run / "judge_items.jsonl") if bench_id(it) in wanted]
        write_jsonl(out / f"{run}.judge_items.jsonl", items)
        print(run, len(items), "judge items")
    (out / "sample.json").write_text(json.dumps({"seed": SAMPLE_SEED, "size": len(ids), "item_ids": ids}, indent=1),
                                     encoding="utf-8")
    return 0


def finals(audit_run: str) -> dict:
    """{judge item id: {check: final}} with adjudicated finals filling empty panel ones."""
    out = {}
    for d in read_jsonl(AUDIT_DIR / "runs" / audit_run / "panel.jsonl"):
        out[d["item_id"]] = {c: v.get("final") for c, v in (d.get("checks") or {}).items()}
    adj = AUDIT_DIR / "runs" / audit_run / "adjudicated.jsonl"
    for row in read_jsonl(adj) if adj.exists() else []:
        if out.get(row["item_id"], {}).get(row["check"]) is None:
            out.setdefault(row["item_id"], {})[row["check"]] = row["final"]
    return out


def per_question(run: str, audit_run: str, ids: list) -> tuple:
    """({question: (sentences passing, sentences decided)}, {question: (answer not passing, decided)}, undecided)."""
    f = finals(audit_run)
    sup = {i: [0, 0] for i in ids}
    ans = {i: [0, 0] for i in ids}
    undecided = 0
    for it in read_jsonl(CONFIRM / "guardrail" / f"{run}.judge_items.jsonl"):
        q = bench_id(it)
        check = "supports" if it.get("kind", "sentence") == "sentence" else "answers"
        final = (f.get(it["item_id"]) or {}).get(check)
        if final is None:
            undecided += 1
            continue
        if check == "supports":
            sup[q][0] += final == "pass"
            sup[q][1] += 1
        else:
            ans[q][0] += final != "pass"
            ans[q][1] += 1
    return sup, ans, undecided


def ratio(table: dict, keys: list) -> float:
    den = sum(table[k][1] for k in keys)
    return sum(table[k][0] for k in keys) / den if den else float("nan")


def boot(ids: list, fn) -> list:
    rng = random.Random(BOOT_SEED)
    vals = []
    for _ in range(RESAMPLES):
        s = [ids[rng.randrange(len(ids))] for _ in ids]
        vals.append(fn(s))
    vals.sort()
    return [vals[int(0.025 * RESAMPLES)], vals[int(0.975 * RESAMPLES) - 1]]


def cmd_guardrail(args) -> int:
    ids = json.loads((CONFIRM / "guardrail" / "sample.json").read_text(encoding="utf-8"))["item_ids"]
    s1, a1, u1 = per_question(V1, args.audit[0], ids)
    s2, a2, u2 = per_question(CAND, args.audit[1], ids)
    res = {}
    for name, t1, t2, bad in (("supports_strict", s1, s2, "upper_below"), ("answers_failure", a1, a2, "lower_above")):
        diff = ratio(t2, ids) - ratio(t1, ids)
        ci = boot(ids, lambda s: ratio(t2, s) - ratio(t1, s))
        fails = ci[1] < -MARGIN if bad == "upper_below" else ci[0] > MARGIN
        res[name] = {"v1": ratio(t1, ids), "candidate": ratio(t2, ids), "difference": diff, "bootstrap95": ci,
                     "v1_n": sum(t1[k][1] for k in ids), "candidate_n": sum(t2[k][1] for k in ids),
                     "guardrail": "fails" if fails else "holds"}
    res["undecided"] = {"v1": u1, "candidate": u2}
    res["holds"] = all(res[k]["guardrail"] == "holds" for k in ("supports_strict", "answers_failure"))
    out = CONFIRM / "guardrail" / "guardrail.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


def fr_table(root: Path, v1: str, cand: str) -> dict:
    """{question: (v1 refused, candidate refused)} over answerable questions both runs answered without error."""
    a, b = answers(root, v1), answers(root, cand)
    out = {}
    for i in a:
        if i in b and ok(a[i]) and ok(b[i]) and not a[i]["should_refuse"]:
            out[i] = (1 if a[i].get("refused") else 0, 1 if b[i].get("refused") else 0)
    return out


def cmd_pooled(args) -> int:
    sets = [fr_table(BENCH, TEST_V1, TEST_CAND), fr_table(CONFIRM, V1, CAND)]
    keys = [sorted(t) for t in sets]

    def diff(samples):
        n = sum(len(s) for s in samples)
        r1 = sum(t[k][0] for t, s in zip(sets, samples) for k in s)
        r2 = sum(t[k][1] for t, s in zip(sets, samples) for k in s)
        return (r2 - r1) / n

    point = diff(keys)
    rng = random.Random(BOOT_SEED)
    vals = []
    for _ in range(RESAMPLES):
        vals.append(diff([[ks[rng.randrange(len(ks))] for _ in ks] for ks in keys]))
    vals.sort()
    ci = [vals[int(0.025 * RESAMPLES)], vals[int(0.975 * RESAMPLES) - 1]]
    res = {"sets": {"frozen_test": len(keys[0]), "confirm1": len(keys[1])},
           "v1_rate": sum(t[k][0] for t, ks in zip(sets, keys) for k in ks) / sum(len(k) for k in keys),
           "candidate_rate": sum(t[k][1] for t, ks in zip(sets, keys) for k in ks) / sum(len(k) for k in keys),
           "difference": point, "bootstrap95": ci, "passes": ci[1] <= MARGIN}
    (CONFIRM / "pooled_false_refusals.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample")
    p = sub.add_parser("guardrail")
    p.add_argument("--audit", nargs=2, required=True, help="audit runs for v1 and the candidate, in that order")
    sub.add_parser("pooled")
    args = parser.parse_args(argv)
    return {"sample": cmd_sample, "guardrail": cmd_guardrail, "pooled": cmd_pooled}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
