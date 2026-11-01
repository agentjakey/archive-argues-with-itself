"""Choose the audit panel against labels (silver labels until the author's land), by the judge bar.

    python scripts/v2/choose_panel.py --run kit2-judges --labels reports/v2/audit/reference/silver_labels.jsonl

The judges' verdicts come from one run in which every candidate and the escalation judge read every
kit item (kit2-judges), so any panel can be simulated without new calls. Panels considered:
  pair       two judges from two families, the escalation judge deciding their disagreements, then a
             person (the configured panel rule);
  majority   three judges from three families, the majority class decides, the escalation judge
             breaks a three-way split, then a person;
  sonnet2    for SUPPORTS only: one candidate with the escalation judge as the second judge, and
             their disagreements to a person.
Candidates exclude the model that wrote the answers and any reference judge. Each panel is measured
per check with audit/calibration.py compare (kappa, not-pass recall, false-pass and error bounds, the
bar) against the labels, against each reference judge alone (to show any family lean), and costed per
item from the run's actual spend: each judge's mean cost per item it read, the escalation judge's cost
times the share of items escalated.

Decision rule (Jake, 2026-11-01): the cheapest pair meeting the bar on every check with enough labels.
If no pair meets it on SUPPORTS, SUPPORTS uses the three-judge majority or Sonnet as its second judge,
whichever meets the bar at lower cost; the other checks keep the cheapest pair that meets them.
Writes panel_choice.json and panel_choice.md beside the labels. Reads files only."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import calibration, judges, panel, prompts  # noqa: E402
from archive_debugger.audit.records import read_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, good_judgments  # noqa: E402

CANDIDATES = ("claude-haiku-5-5", "gpt-oss-120b", "deepseek-v4-flash")


def load_labels(path: Path) -> dict:
    latest = {}
    for row in read_jsonl(path):
        latest[row["item_id"]] = row
    out = {c: {} for c in prompts.CHECKS}
    for item_id, row in latest.items():
        for c in prompts.CHECKS:
            if row.get(c):
                out[c][item_id] = row[c]
    return out


def pair_finals(done, items, a, b, escalation, check):
    finals, escalated = {}, 0
    for it in items:
        if check not in prompts.KIND_CHECKS[prompts.kind_of(it)]:
            continue
        va, vb = panel.vote(done.get((it["item_id"], a)), check), panel.vote(done.get((it["item_id"], b)), check)
        if va is not None and va == vb:
            finals[it["item_id"]] = va
            continue
        if escalation is None:
            finals[it["item_id"]] = None
            continue
        escalated += 1
        ve = panel.vote(done.get((it["item_id"], escalation)), check)
        finals[it["item_id"]] = ve if ve is not None and ve in (va, vb) else None
    return finals, escalated


def majority_finals(done, items, trio, escalation, check):
    finals, escalated = {}, 0
    for it in items:
        if check not in prompts.KIND_CHECKS[prompts.kind_of(it)]:
            continue
        votes = [panel.vote(done.get((it["item_id"], n)), check) for n in trio]
        counts = Counter(v for v in votes if v is not None)
        top = counts.most_common(1)
        if top and top[0][1] >= 2:
            finals[it["item_id"]] = top[0][0]
            continue
        escalated += 1
        ve = panel.vote(done.get((it["item_id"], escalation)), check)
        finals[it["item_id"]] = ve if ve is not None and ve in counts else None
    return finals, escalated


def per_item_cost(run_dir: Path) -> dict:
    spent, seen = Counter(), Counter()
    for rec in read_jsonl(run_dir / "judgments.jsonl"):
        spent[rec["judge"]] += rec.get("usd") or 0.0
        seen[rec["judge"]] += 1
    return {j: spent[j] / seen[j] for j in seen if seen[j]}


def measure(labels_c, finals, refs_c):
    m = calibration.compare(labels_c, finals)
    out = {k: m[k] for k in ("items_labeled", "items_decided", "items_to_human", "kappa_binary", "error_rate",
                             "error_wilson", "false_pass", "missed_failures", "not_pass_recall", "skewed", "bar")}
    out["by_reference"] = {name: calibration.compare(lab, finals)["kappa_binary"] for name, lab in refs_c.items()}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default="kit2-judges")
    parser.add_argument("--labels", type=Path, default=AUDIT_DIR / "reference" / "silver_labels.jsonl")
    parser.add_argument("--reference-run", default="ref-kit-1")
    args = parser.parse_args(argv)
    cfg = judges.load_panel()
    run_dir = AUDIT_DIR / "runs" / args.run
    items = read_jsonl(run_dir / "items.jsonl")
    done = good_judgments(run_dir / "judgments.jsonl")
    labels = load_labels(args.labels)
    ref_done = good_judgments(AUDIT_DIR / "runs" / args.reference_run / "judgments.jsonl")
    refs = {c: {name: {it["item_id"]: panel.vote(ref_done.get((it["item_id"], name)), c) for it in items
                       if c in prompts.KIND_CHECKS[prompts.kind_of(it)] and panel.vote(ref_done.get((it["item_id"], name)), c)}
                for name in cfg.references} for c in prompts.CHECKS}
    writers = {it.get("writer_model") for it in items if it.get("writer_model")}
    candidates = [n for n in CANDIDATES if n in cfg.specs and n not in cfg.references
                  and not any(judges.same_model(cfg.specs[n].model, w) for w in writers)]
    cost = per_item_cost(run_dir)
    esc = cfg.escalation
    options = []
    for c in prompts.CHECKS:
        n_items = sum(1 for it in items if c in prompts.KIND_CHECKS[prompts.kind_of(it)])
        for a, b in itertools.combinations(candidates, 2):
            if cfg.specs[a].family == cfg.specs[b].family:
                continue
            finals, escalated = pair_finals(done, items, a, b, esc, c)
            options.append({"check": c, "kind": "pair", "judges": [a, b], "escalation": esc,
                            "usd_per_item": cost.get(a, 0) + cost.get(b, 0) + cost.get(esc, 0) * escalated / n_items,
                            "escalated_share": escalated / n_items, **measure(labels[c], finals, refs[c])})
        if len(candidates) >= 3:
            trio = tuple(candidates[:3])
            finals, escalated = majority_finals(done, items, trio, esc, c)
            options.append({"check": c, "kind": "majority", "judges": list(trio), "escalation": esc,
                            "usd_per_item": sum(cost.get(n, 0) for n in trio) + cost.get(esc, 0) * escalated / n_items,
                            "escalated_share": escalated / n_items, **measure(labels[c], finals, refs[c])})
        if c == "supports":
            for a in candidates:
                finals, _ = pair_finals(done, items, a, esc, None, c)
                options.append({"check": c, "kind": "sonnet2", "judges": [a, esc], "escalation": None,
                                "usd_per_item": cost.get(a, 0) + cost.get(esc, 0), "escalated_share": 0.0,
                                **measure(labels[c], finals, refs[c])})

    def best(check, kinds):
        ok = [o for o in options if o["check"] == check and o["kind"] in kinds and o["bar"]["meets"]]
        return min(ok, key=lambda o: o["usd_per_item"]) if ok else None

    pairs_all = {}
    for a, b in itertools.combinations(candidates, 2):
        if cfg.specs[a].family == cfg.specs[b].family:
            continue
        rows = [o for o in options if o["kind"] == "pair" and o["judges"] == [a, b]]
        pairs_all[f"{a} + {b}"] = {"meets": {o["check"]: o["bar"]["meets"] for o in rows},
                                   "usd_per_item": max(o["usd_per_item"] for o in rows)}
    full = [n for n, v in pairs_all.items() if all(v["meets"].values())]
    choice = {}
    if full:
        name = min(full, key=lambda n: pairs_all[n]["usd_per_item"])
        choice = {c: {"kind": "pair", "judges": name.split(" + ")} for c in prompts.CHECKS}
        rule = f"the cheapest pair meeting the bar on every check: {name}"
    else:
        for c in prompts.CHECKS:
            pick = best(c, ("pair",))
            if pick is None and c == "supports":
                pick = best(c, ("majority", "sonnet2"))
            choice[c] = {"kind": pick["kind"], "judges": pick["judges"]} if pick else None
        rule = "no pair meets the bar on every check; each check takes its cheapest option that meets it (SUPPORTS may use the majority or Sonnet as second judge)"

    report = {"run": args.run, "labels": str(args.labels), "labels_by_check": {c: len(v) for c, v in labels.items()},
              "candidates": candidates, "escalation": esc, "references": list(cfg.references),
              "cost_per_item_by_judge": cost, "options": options, "pairs": pairs_all, "choice": choice, "rule": rule}
    out = args.labels.parent / "panel_choice.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    def fmt(o):
        k = f"{o['kappa_binary']:.3f}" if o["kappa_binary"] is not None else "-"
        r = o["not_pass_recall"]
        rec = f"{r['recall']:.2f} (n={r['n']})" if r["recall"] is not None else f"- (n={r['n']})"
        fp = o["false_pass"]
        fpr = f"{fp['rate']:.3f} (to {fp['wilson'][1]:.3f})" if fp["rate"] is not None else "-"
        err = f"{o['error_rate']:.3f} (to {o['error_wilson'][1]:.3f})" if o["error_rate"] is not None else "-"
        byref = ", ".join(f"{n.split('-')[0]} {v:.2f}" if v is not None else f"{n} -" for n, v in o["by_reference"].items())
        return (f"| {o['kind']} | {' + '.join(o['judges'])} | {o['items_decided']}/{o['items_labeled']} | {k} | {rec} | "
                f"{fpr} | {err} | {byref} | ${o['usd_per_item']:.5f} | {'meets' if o['bar']['meets'] else '; '.join(o['bar']['reasons'])} |")

    lines = [f"# Panel choice against {args.labels.name}", "",
             f"Labels per check: {report['labels_by_check']}. Candidates: {', '.join(candidates)}; escalation {esc}. "
             f"Judgments from run {args.run}. Kappa by reference shows each panel's agreement with each reference judge alone.", ""]
    for c in prompts.CHECKS:
        lines += [f"## {c}", "", "| Kind | Judges | Decided/labelled | Kappa | Not-pass recall | False-pass (upper) | Error (upper) | Kappa by reference | USD per item | Bar |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        lines += [fmt(o) for o in sorted((o for o in options if o["check"] == c), key=lambda o: o["usd_per_item"])]
        lines.append("")
    lines += ["## Choice", "", f"Rule applied: {rule}.", ""]
    lines += [f"- {c}: {v['kind']} {' + '.join(v['judges'])}" if v else f"- {c}: nothing meets the bar; stays human-reviewed"
              for c, v in choice.items()]
    (args.labels.parent / "panel_choice.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-(len(choice) + 3):]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
