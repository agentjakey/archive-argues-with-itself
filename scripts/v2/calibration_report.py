"""Measure the judges against the person's calibration labels and choose the panel
(docs/formats/audit.md).

    python scripts/v2/calibration_report.py --run kit2-judges
    python scripts/v2/calibration_report.py --run kit2-judges --labels reports/v2/audit/calibration/labels.jsonl

For every judge that read the kit, and for every allowed panel (two judges from two model families,
neither the model that wrote the answers, with the configured escalation judge for disagreements),
each check is compared with the labels: kappa, not-pass recall, false-pass rate, missed failures and
overall error, with Wilson intervals, and whether the bar is met (audit/calibration.py). Panels are
ranked by the number of checks that meet the bar, then by mean binary kappa. The rule set at Gate 2a:
if Haiku 5.5 and Haiku 4.5 panels come out close, the Haiku 5.5 one is preferred.

Writes calibration_report.json and calibration_report.md beside the labels. Reads files only; no
model is called."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import calibration, judges, panel, prompts  # noqa: E402
from archive_debugger.audit.records import read_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR, good_judgments  # noqa: E402

CLOSE_KAPPA = 0.05     # panels within this mean kappa and the same number of checks met count as close


def human_labels(path: Path) -> dict:
    """{check: {item_id: label}} from the labels file, the last save for an item winning."""
    latest = {}
    for row in read_jsonl(path):
        latest[row["item_id"]] = row
    out = {c: {} for c in prompts.CHECKS}
    for item_id, row in latest.items():
        for c in prompts.CHECKS:
            if row.get(c):
                out[c][item_id] = row[c]
    return out


def judge_verdicts(done: dict, items: list, name: str, check: str) -> dict:
    out = {}
    for it in items:
        if check not in prompts.KIND_CHECKS[prompts.kind_of(it)]:
            continue
        rec = done.get((it["item_id"], name))
        out[it["item_id"]] = panel.vote(rec, check)
    return out


def panel_verdicts(done: dict, items: list, pair: tuple, escalation: str) -> dict:
    """{check: {item_id: final or None}} for a hypothetical panel, from judgments already made."""
    out = {c: {} for c in prompts.CHECKS}
    gate = {"valid": None, "flags": []}
    for it in items:
        d = panel.decide(it, gate, pair, {n: done.get((it["item_id"], n)) for n in pair},
                         done.get((it["item_id"], escalation)))
        for c, v in d["checks"].items():
            out[c][it["item_id"]] = v["final"]
    return out


def allowed_pairs(cfg: judges.PanelConfig, names: list, items: list) -> list:
    writers = {it.get("writer_model") for it in items if it.get("writer_model")}
    ok = [n for n in names if n != cfg.escalation
          and not any(judges.same_model(cfg.specs[n].model, w) for w in writers)]
    return [p for p in itertools.combinations(sorted(ok), 2) if cfg.specs[p[0]].family != cfg.specs[p[1]].family]


def summarize(m: dict) -> dict:
    keep = ("items_labeled", "items_decided", "items_to_human", "exact_agreement", "kappa_binary", "error_rate",
            "error_wilson", "false_pass", "missed_failures", "not_pass_recall", "skewed", "bar")
    return {k: m[k] for k in keep}


def rank(panels: dict) -> list:
    def key(name):
        checks = panels[name]["checks"]
        met = sum(1 for m in checks.values() if m["bar"]["meets"])
        kappas = [m["kappa_binary"] for m in checks.values() if m["kappa_binary"] is not None]
        return (-met, -(sum(kappas) / len(kappas) if kappas else -1.0))
    return sorted(panels, key=key)


def prefer_newer_haiku(order: list, panels: dict, cfg: judges.PanelConfig) -> list:
    """Gate 2a rule: when the top panel holds Haiku 4.5 and the same panel with Haiku 5.5 instead is
    close (same checks met, mean kappa within CLOSE_KAPPA), the Haiku 5.5 one goes first."""
    if not order:
        return order
    top = order[0]
    old = [n for n in panels[top]["pair"] if cfg.specs[n].model.startswith("claude-haiku-4-5")]
    new = [n for n, s in cfg.specs.items() if s.model.startswith("claude-haiku-5-5")]
    if not old or not new:
        return order
    swapped = " + ".join(sorted(new[0] if n == old[0] else n for n in panels[top]["pair"]))
    if swapped not in panels:
        return order
    a, b = panels[top], panels[swapped]
    if a["checks_met"] == b["checks_met"] and abs(a["mean_kappa"] - b["mean_kappa"]) <= CLOSE_KAPPA:
        return [swapped] + [n for n in order if n != swapped]
    return order


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="the audit run that judged the kit")
    parser.add_argument("--labels", type=Path, default=AUDIT_DIR / "calibration" / "labels.jsonl")
    args = parser.parse_args(argv)
    run_dir = AUDIT_DIR / "runs" / args.run
    items = read_jsonl(run_dir / "items.jsonl")
    done = good_judgments(run_dir / "judgments.jsonl")
    labels = human_labels(args.labels)
    if not any(labels.values()):
        raise SystemExit(f"no labels in {args.labels} yet")
    cfg = judges.load_panel()
    names = sorted({name for _, name in done})

    per_judge = {}
    for name in names:
        per_judge[name] = {c: summarize(calibration.compare(labels[c], judge_verdicts(done, items, name, c)))
                           for c in prompts.CHECKS}
    panels = {}
    for pair in allowed_pairs(cfg, names, items):
        finals = panel_verdicts(done, items, pair, cfg.escalation)
        checks = {c: summarize(calibration.compare(labels[c], finals[c])) for c in prompts.CHECKS}
        kappas = [m["kappa_binary"] for m in checks.values() if m["kappa_binary"] is not None]
        panels[" + ".join(pair)] = {"pair": list(pair), "checks": checks,
                                    "checks_met": sum(1 for m in checks.values() if m["bar"]["meets"]),
                                    "mean_kappa": sum(kappas) / len(kappas) if kappas else None}
    order = prefer_newer_haiku(rank(panels), panels, cfg)
    report = {"run": args.run, "labels": str(args.labels), "labels_by_check": {c: len(v) for c, v in labels.items()},
              "escalation": cfg.escalation, "judges": per_judge, "panels": panels, "ranking": order,
              "recommended": order[0] if order else None}
    out_json = args.labels.parent / "calibration_report.json"
    out_json.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    def row(name, m):
        k = f"{m['kappa_binary']:.3f}" if m["kappa_binary"] is not None else "-"
        r = m["not_pass_recall"]
        rec = f"{r['recall']:.2f} ({r['wilson'][0]:.2f}-{r['wilson'][1]:.2f}), n={r['n']}" if r["recall"] is not None else f"-, n={r['n']}"
        fp = m["false_pass"]
        fpr = f"{fp['rate']:.3f} (to {fp['wilson'][1]:.3f})" if fp["rate"] is not None else "-"
        err = f"{m['error_rate']:.3f} (to {m['error_wilson'][1]:.3f})" if m["error_rate"] is not None else "-"
        return (f"| {name} | {m['items_decided']} / {m['items_labeled']} | {k} | {rec} | {fpr} | "
                f"{m['missed_failures']['count']} of {m['missed_failures']['of_human_not_pass']} | {err} | "
                f"{'meets' if m['bar']['meets'] else '; '.join(m['bar']['reasons'])} |")

    head = ["| Judge or panel | Decided / labelled | Kappa | Not-pass recall (95%) | False-pass rate (upper) | "
            "Missed failures | Error (upper) | Bar |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines = [f"# Calibration report: run {args.run}", "",
             f"Labels: {report['labels_by_check']} (author-reviewed). Escalation judge: {cfg.escalation}.", ""]
    for c in prompts.CHECKS:
        lines += [f"## {c}", ""] + head
        lines += [row(n, per_judge[n][c]) for n in names]
        lines += [row("PANEL " + n, panels[n]["checks"][c]) for n in order]
        lines.append("")
    lines += ["## Ranking", ""] + [f"{i + 1}. {n}: {panels[n]['checks_met']} of 3 checks meet the bar, mean kappa "
                                   f"{panels[n]['mean_kappa'] if panels[n]['mean_kappa'] is None else round(panels[n]['mean_kappa'], 3)}"
                                   for i, n in enumerate(order)]
    (args.labels.parent / "calibration_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"recommended panel: {report['recommended']}; report: {args.labels.parent / 'calibration_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
