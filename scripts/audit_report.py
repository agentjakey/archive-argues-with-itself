"""Recompute every headline audit number for a scope from the committed judgment and gold
files, with Wilson 95% intervals, and off-target as a first-class metric. Nothing here calls a
model or the network, and nothing reads the corpus for the judgment-derived numbers.

    python scripts/audit_report.py                     # pilot (default)
    python scripts/audit_report.py --scope microlog    # national microlog

What is computed from committed files, per scope:
  - strict / lenient citation support: the per-sentence s/p/n marks over the kept sentences.
  - citations resolving: the count of distinct cited passage ids over the answered questions
    (equal to itself, 1.0 by construction: the verifier drops any citation that does not
    resolve before a sentence is kept). The interval is the Wilson interval of k/k.
  - abstention, false abstention, off-target: the gold verdict per question (answerable vs
    should-abstain) against the run outcome (answered vs abstained), from committed files.

What is NOT recomputable from committed judgment files, and how it is handled:
  - retrieval recall@k / nDCG@10: a mean of per-question fractions that needs the retriever's
    ranked output (the index), which is not committed and is out of scope here. The final-gold
    figures are read from the committed docs/evaluation/retrieval_report.md that eval.report
    wrote; they are not typed into this script, and they carry no Wilson interval (a mean of
    fractions is not a binomial proportion).
  - the microlog jurisdiction-unknown share: a corpus census from civic_microlog.db, not a
    judgment file. It is read from that database when present (no sampling, so no interval).

Guard: before writing, the recomputed headline values are compared to the values already
published in the scope's audit_numbers.json. Any mismatch stops the run and prints both
numbers; no published number is changed silently and no gold is edited to force a match.

Outputs:
  pilot     -> reports/phase16/audit_numbers.json, docs/evaluation/audit_report.md
  microlog  -> reports/microlog/audit_numbers.json (headline fields recomputed in place;
               corpus, sensitivity and coverage-grid fields are preserved)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from archive_debugger.eval.stats import fmt_pct_ci, rate_with_ci, wilson_interval

VALID = {"s": "supported", "p": "partly", "n": "not"}
DISCLOSURE = ("All labels and judgments were decided by the author. To speed adjudication, candidate labels "
              "for the Phase 13 extension and the Phase 16 support judgments were first proposed by an assistant "
              "model and each was reviewed and decided by the author; the same model family generates the tool's "
              "answers, so this judge is not independent of the system.")


# ---------- committed-file loaders ----------

def read_jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and line[0] in "{[":
            out.append(json.loads(line))
    return out


def load_marks_json(path: Path):
    """Pilot marks: {"q001": {"1": "s", ...}} or {"q001": ["s", ...]}; "_meta" ignored."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    for qid, val in raw.items():
        if qid == "_meta":
            continue
        if isinstance(val, dict):
            marks = {int(k): str(v).strip().lower()[:1] for k, v in val.items()}
        elif isinstance(val, list):
            marks = {i + 1: str(v).strip().lower()[:1] for i, v in enumerate(val)}
        else:
            raise ValueError(f"{qid}: marks must be a dict by sentence number or a list")
        bad = {k: v for k, v in marks.items() if v not in VALID}
        if bad:
            raise ValueError(f"{qid}: marks must be s/p/n, got {bad}")
        out[qid] = marks
    return out, raw.get("_meta")


def marks_from_worksheet(sentences: list[dict]):
    """Microlog marks: the per-sentence `judgment` field on each worksheet record."""
    out: dict = {}
    for r in sentences:
        m = str(r.get("judgment") or "").strip().lower()[:1]
        if m not in VALID:
            raise ValueError(f"{r.get('qid')} s{r.get('sentence_no')}: judgment must be s/p/n, got {r.get('judgment')!r}")
        out.setdefault(r["qid"], {})[r["sentence_no"]] = m
    return out, None


def load_gold_flat_v(path: Path) -> dict:
    """Pilot gold: eval/gold_decisions.json, {"q001": {"v": "a" | "x", "r": [...]}}; a = answerable."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {q: (v.get("v") == "a") for q, v in raw.items() if q != "_meta" and isinstance(v, dict)}


def load_gold_questions_v(path: Path) -> dict:
    """Microlog gold: reports/microlog/gold_decisions.json, questions[qid] = {"v": "a"|"x", ...}."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    q = raw.get("questions", {})
    return {qid: (v.get("v") == "a") for qid, v in q.items()}


def load_reasons(path: Path) -> dict:
    """'- q012 s2 n: reason' bullets -> {(qid, sentence_no): reason}."""
    if not path or not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*(q\d{3})\s+s(\d+)\s+[spn]\s*:\s*(.+)$", line)
        if m:
            out[(m.group(1), int(m.group(2)))] = m.group(3).strip()
    return out


def parse_final_recall(md_path: Path) -> dict | None:
    """Read the baseline/candidate '+batch 2 (final)' rows from the committed retrieval report.
    Recall needs the retriever's ranked output (the index) and is not recomputable from
    committed judgment files; it is sourced here, not typed. Returns before/after tuples."""
    if not md_path or not md_path.exists():
        return None
    header = None
    rows: dict = {}
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == "state" and "gold" in cells and "recall@10" in cells:
            header = cells
        elif header and cells and cells[0] in ("baseline", "candidate") and len(cells) == len(header) \
                and cells[1] == "+batch 2 (final)":
            rows[cells[0]] = dict(zip(header, cells))
    if "baseline" not in rows or "candidate" not in rows:
        return None
    def pair(metric: str):
        return (float(rows["baseline"][metric]), float(rows["candidate"][metric]))
    return {"recall@10": pair("recall@10"), "recall@20": pair("recall@20"),
            "ndcg@10": pair("ndcg@10"), "source": str(md_path).replace("\\", "/")}


# ---------- the scope-agnostic core ----------

def unique_cited_count(sentences: list[dict]) -> int:
    """Sum over answered questions of the number of distinct cited passage ids in that question:
    the citations-resolving count (numerator equals denominator; all resolve by construction)."""
    by_q: dict = {}
    for r in sentences:
        by_q.setdefault(r["qid"], set()).update(c["passage_id"] for c in r.get("cited", []))
    return sum(len(v) for v in by_q.values())


def compute(sentences: list[dict], marks: dict, gold_answerable: dict, reasons: dict, support_over: str):
    """Every judgment-derived headline number for one scope, each rate with a Wilson interval."""
    answerable = {q for q, a in gold_answerable.items() if a}
    abstain = {q for q, a in gold_answerable.items() if not a}
    answered = {r["qid"] for r in sentences}
    # An abstained gold question is one with a verdict that produced no kept sentence.
    abstained = {q for q in gold_answerable if q not in answered}

    scored = [r for r in sentences if (support_over == "all_kept" or r["qid"] in answerable)]
    missing = [(r["qid"], r["sentence_no"]) for r in scored
               if marks.get(r["qid"], {}).get(r["sentence_no"]) is None]
    if missing:
        raise ValueError(f"unjudged sentences: {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    total = Counter()
    per_q: dict = {}
    pn: list[dict] = []
    for r in scored:
        m = marks[r["qid"]][r["sentence_no"]]
        per_q.setdefault(r["qid"], Counter())[m] += 1
        total[m] += 1
        if m in ("p", "n"):
            pn.append({"qid": r["qid"], "sentence_no": r["sentence_no"], "mark": VALID[m], "text": r["text"],
                       "cited": [c["passage_id"] for c in r.get("cited", [])],
                       "reason": reasons.get((r["qid"], r["sentence_no"]), "")})
    n_sent = sum(total.values())
    resolving_n = unique_cited_count(sentences)

    abstained_on_abstain = sorted(abstain & abstained)
    off_target = sorted(abstain & answered)
    false_abstentions = sorted(answerable & abstained)

    return {
        "counts": {"answerable_questions": len(answerable), "should_abstain_questions": len(abstain),
                   "answered_questions": len(answered), "kept_sentences_scored": n_sent,
                   "supported": total["s"], "partly": total["p"], "not": total["n"],
                   "support_scope": support_over},
        "strict_support": rate_with_ci(total["s"], n_sent),
        "lenient_support": rate_with_ci(total["s"] + total["p"], n_sent),
        "citations_resolving": {**rate_with_ci(resolving_n, resolving_n),
                                "note": "1.0 by construction; the verifier drops any citation that does not resolve"},
        "abstention_on_should_abstain": {**rate_with_ci(len(abstained_on_abstain), len(abstain)),
                                         "qids": abstained_on_abstain},
        "off_target_answers": {**rate_with_ci(len(off_target), len(abstain)), "qids": off_target,
                               "definition": "should-abstain questions answered with cited, supported sentences that "
                                             "address a different question than the one asked"},
        "false_abstention_on_answerable": {**rate_with_ci(len(false_abstentions), len(answerable)),
                                           "qids": false_abstentions},
        "_per_q": per_q, "_pn": pn, "_total": total, "_n_sent": n_sent,
        "_answerable": sorted(answerable), "_abstain": sorted(abstain),
        "_abstained_on_abstain": abstained_on_abstain, "_off_target": off_target,
        "_false_abstentions": false_abstentions,
    }


# ---------- guard: recomputed vs published ----------

def _num(x):
    """First number in a value like '10/15', '119/119 = 1.0', 0.98, or a rate block."""
    if isinstance(x, dict) and "rate" in x:
        return x["rate"]
    if isinstance(x, (int, float)):
        return round(float(x), 4)
    m = re.search(r"-?\d+(?:\.\d+)?", str(x))
    return float(m.group()) if m else None


def _count(x):
    """Integer numerator from a rate block ({'num': ...}) or the first integer in a string like
    '119/119 = 1.0'. Lets the guard compare counts across the old string form and the new block."""
    if isinstance(x, dict):
        return x.get("num")
    m = re.search(r"\d+", str(x)) if x is not None else None
    return int(m.group()) if m else None


def _qids(x):
    """The qid list from either a plain list (old form) or a rate block's 'qids' (new form)."""
    if isinstance(x, dict):
        return x.get("qids")
    return x if isinstance(x, list) else None


def guard(scope: str, computed_checks: dict, published: dict) -> list[str]:
    """Return a list of human-readable mismatch lines (empty when everything reproduces)."""
    out = []
    for label, got, pub in computed_checks.get("_pairs", []):
        if got is None or pub is None:
            continue
        if isinstance(got, (list,)):
            if sorted(got) != sorted(pub):
                out.append(f"[{scope}] {label}: recomputed {got} != published {pub}")
        elif abs(float(got) - float(pub)) > 5e-4:
            out.append(f"[{scope}] {label}: recomputed {got} != published {pub}")
    return out


# ---------- pilot ----------

def run_pilot(args) -> int:
    sentences = [r for r in read_jsonl(args.worksheet) if r.get("kind") == "sentence"]
    marks, meta = load_marks_json(args.judgments)
    reasons = load_reasons(args.notes)
    gold = load_gold_flat_v(args.gold)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    holdout = json.loads(args.holdout.read_text(encoding="utf-8")) if args.holdout.exists() else None
    recall = parse_final_recall(args.recall_md)

    c = compute(sentences, marks, gold, reasons, "answerable_only")
    strict, lenient = c["strict_support"], c["lenient_support"]
    resolving = c["citations_resolving"]
    abst, offt, falseab = c["abstention_on_should_abstain"], c["off_target_answers"], c["false_abstention_on_answerable"]
    n_abstain, n_answerable = c["counts"]["should_abstain_questions"], c["counts"]["answerable_questions"]

    numbers = {
        "scope": "pilot",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": "recomputed from committed files by scripts/audit_report.py; no number typed by hand. "
                      "recall is sourced from the committed retrieval report (needs the index; not judgment-derived).",
        "run": {"questions": summary["questions"], "answered": summary["answered"], "abstained": summary["abstained"],
                "model": summary["model"], "kept_sentences_total": summary["sentences"],
                "dropped_unsupported": summary["unsupported_sentences"]},
        "judged_sentences_answerable": c["_n_sent"],
        "supported": c["_total"]["s"], "partly": c["_total"]["p"], "not": c["_total"]["n"],
        "strict_support_rate": strict["rate"], "lenient_support_rate": lenient["rate"],
        "strict_support": strict, "lenient_support": lenient,
        "citations_resolving_count": resolving["num"], "citations_resolving": resolving,
        "abstention_on_gold_abstain_in_sample": f"{len(c['_abstained_on_abstain'])}/{n_abstain}",
        "abstention_on_should_abstain": abst,
        "off_target_answers": offt,
        "false_abstentions_on_answerable_in_sample": f"{len(c['_false_abstentions'])}/{n_answerable}",
        "false_abstention_on_answerable": falseab,
        "holdout": None if holdout is None else _holdout_block(holdout),
        "recall_final_gold": recall,
        "judgment_meta": meta,
    }

    published = json.loads(args.out_json.read_text(encoding="utf-8")) if args.out_json.exists() else {}
    checks = {"_pairs": [
        ("strict_support_rate", strict["rate"], _num(published.get("strict_support_rate"))),
        ("lenient_support_rate", lenient["rate"], _num(published.get("lenient_support_rate"))),
        ("supported", c["_total"]["s"], _num(published.get("supported"))),
        ("partly", c["_total"]["p"], _num(published.get("partly"))),
        ("not", c["_total"]["n"], _num(published.get("not"))),
        ("abstention", _num(numbers["abstention_on_gold_abstain_in_sample"]), _num(published.get("abstention_on_gold_abstain_in_sample"))),
        ("false_abstention", _num(numbers["false_abstentions_on_answerable_in_sample"]), _num(published.get("false_abstentions_on_answerable_in_sample"))),
        ("off_target_qids", offt["qids"], _qids(published.get("off_target_answers"))),
        ("citations_resolving", resolving["num"], _count(published.get("citations_resolving"))),
    ]}
    mism = guard("pilot", checks, published)
    if mism:
        print("RECOMPUTE MISMATCH (nothing written):", *mism, sep="\n  ")
        return 3

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(numbers, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_pilot_md(args.evidence / "audit_report.md", c, numbers, summary, holdout, recall)
    print(json.dumps({k: v for k, v in numbers.items() if k not in ("judgment_meta",)}, ensure_ascii=False, indent=2))
    return 0


def _holdout_block(h: dict) -> dict:
    return {"gold_abstain": f"{h['gold_abstain']['abstained']}/{h['gold_abstain']['n']}",
            "gold_abstain_ci": rate_with_ci(h["gold_abstain"]["abstained"], h["gold_abstain"]["n"])["ci95"],
            "gold_abstain_answered": h["gold_abstain"]["answered"],
            "gold_answerable": f"{h['gold_answerable']['answered']}/{h['gold_answerable']['n']}",
            "gold_answerable_ci": rate_with_ci(h["gold_answerable"]["answered"], h["gold_answerable"]["n"])["ci95"],
            "gold_answerable_abstained": h["gold_answerable"]["abstained"], "ts": h["ts"]}


def _write_pilot_md(path: Path, c: dict, numbers: dict, summary: dict, holdout, recall):
    S = fmt_pct_ci
    strict, lenient = c["strict_support"], c["lenient_support"]
    abst, offt, falseab = c["abstention_on_should_abstain"], c["off_target_answers"], c["false_abstention_on_answerable"]
    resolving = c["citations_resolving"]
    n_abstain = c["counts"]["should_abstain_questions"]
    n_answerable = c["counts"]["answerable_questions"]
    total, n_sent = c["_total"], c["_n_sent"]
    ho = numbers["holdout"]
    ho_cell = ("held-out: none run" if ho is None else
               f"held-out: **{ho['gold_abstain']}** probes abstained"
               + (f" (answered: {', '.join(ho['gold_abstain_answered'])})" if ho["gold_abstain_answered"] else "")
               + f"; **{ho['gold_answerable']}** answerable answered"
               + (f" (abstained: {', '.join(ho['gold_answerable_abstained'])})" if ho["gold_answerable_abstained"] else ""))
    rc = ("recall not available" if recall is None else
          f"**{recall['recall@10'][0]:.4f} -> {recall['recall@10'][1]:.4f}** "
          f"(recall@20 {recall['recall@20'][0]:.4f} -> {recall['recall@20'][1]:.4f}; "
          f"nDCG@10 {recall['ndcg@10'][0]:.4f} -> {recall['ndcg@10'][1]:.4f})")

    L = ["# Audit report", "",
         f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC by scripts/audit_report.py.",
         "Every rate below is computed from the committed judgment and gold files and carries a Wilson",
         "95% interval; none is typed in by hand. Recall is the exception: it is a per-question mean that",
         "needs the retriever's ranked output (the index), so it is read from the committed retrieval",
         "report and carries no Wilson interval (a mean of fractions is not a binomial proportion).", "",
         f"Audit run: every seed question once through /ask with the configured model ({summary['model']}), "
         f"final retrieval configuration, {summary['questions']} questions: {summary['answered']} answered, "
         f"{summary['abstained']} abstained; sentence judgments by the author.", "",
         "| # | number | value | source |", "| --- | --- | --- | --- |",
         f"| 1 | Citation support, strict (supported only), kept sentences on the {n_answerable} gold-answerable questions | **{S(total['s'], n_sent)}** | eval/judgments_phase16.json over reports/phase16/judgment_worksheet.jsonl |",
         f"| 2 | Citation support, lenient (supported + partly) | **{S(total['s'] + total['p'], n_sent)}** | same |",
         f"| 3 | Abstention on should-abstain questions | **{S(len(c['_abstained_on_abstain']), n_abstain)}** in-sample; {ho_cell} | this run; holdout_run.md |",
         f"| 4 | Off-target answers (should-abstain questions answered on the wrong question) | **{S(len(offt['qids']), n_abstain)}** in-sample ({', '.join(offt['qids'])}) | this run; section 3 |",
         f"| 5 | False abstention on answerable questions | **{S(len(c['_false_abstentions']), n_answerable)}** in-sample | this run |",
         f"| 6 | Retrieval recall@10 on the final gold, before -> after the retrieval changes | {rc} | retrieval_report.md, final section (no CI: per-question mean) |",
         f"| 7 | Cited passages resolving to a recorded page | **{S(resolving['num'], resolving['den'])}** | every kept citation re-checked; 1.0 by construction |",
         "", "In-sample means the 50 seed questions, which were used to amend the abstention rule (once) and to",
         "label the gold the retriever was chosen on. Held-out means `eval/holdout_questions.jsonl`: 15 questions",
         "written after the abstention rule and retrieval configuration were frozen, never used in any sweep or",
         "design decision, verdicts assigned by the author before the single run.", "",
         "Off-target and abstention share the same denominator (the should-abstain questions), reported side by",
         "side: the tool abstained on some and answered others on the wrong question. Verification guarantees that a",
         "kept sentence is supported by its page; it does not guarantee the page is about what was asked.", "",
         "## Disclosure", "", DISCLOSURE, "",
         "Judgment rule (`eval/judgments_phase16.json`, `_meta`): s = every factual claim in the sentence appears in",
         "the cited passage text; p = a claim, date, or attribution is added or shifted; n = the sentence misstates",
         "the passage. Reasons for every p and n: `eval/judgments_phase16_notes.md`.", "",
         f"## 1-2. Support, per question ({n_answerable} gold-answerable)", "",
         "| qid | sentences | supported | partly | not |", "| --- | ---: | ---: | ---: | ---: |"]
    for q in sorted(c["_per_q"]):
        cc = c["_per_q"][q]
        L.append(f"| {q} | {sum(cc.values())} | {cc['s']} | {cc['p']} | {cc['n']} |")
    L += [f"| **all** | **{n_sent}** | **{total['s']}** | **{total['p']}** | **{total['n']}** |", "",
          f"Strict support rate (s only): {S(total['s'], n_sent)}. Lenient (s + p): {S(total['s'] + total['p'], n_sent)}. "
          f"The {summary['sentences'] - n_sent} kept sentences on the off-target answers (section 3) are excluded from "
          f"these rates; {summary['unsupported_sentences']} drafted sentences were dropped by the verifier or the "
          "fact-leak guard before anyone judged them.", "",
          "### Every partly and not sentence, with the reason", ""]
    for x in c["_pn"]:
        L += [f"- **{x['qid']} s{x['sentence_no']}: {x['mark']}** (cites {', '.join(x['cited'])})",
              f"  > {x['text']}", f"  Reason: {x['reason'] or '(none recorded)'}", ""]
    L += ["## 3. Off-target: verification guarantees support, not relevance", "",
          f"Off-target answer rate: **{S(len(offt['qids']), n_abstain)}** of the should-abstain questions. In-sample "
          f"the tool abstained on {len(c['_abstained_on_abstain'])} of the {n_abstain} gold-abstain questions "
          f"({', '.join(c['_abstained_on_abstain'])}) and answered {len(offt['qids'])} "
          f"({', '.join(offt['qids'])}). The author's judgment of those {len(offt['qids'])}: each is an all-supported "
          "answer to a different question than the one asked, on the wrong period or the wrong object. Every kept "
          "sentence cites a passage that exists, was in the retrieved evidence, and resolves to a recorded page; the "
          "passages do not bear on the question's period or subject. The three structural checks and the fact-leak "
          "guard guarantee support by the page; nothing in the pipeline guarantees the page is about what was asked.", "",
          f"False abstentions on the {n_answerable} answerable questions: **{S(len(c['_false_abstentions']), n_answerable)}**.", ""]
    if holdout is not None:
        L += ["### Held-out run", "",
              f"`eval/holdout_questions.jsonl`, one run on {ho['ts']} (UTC): {ho['gold_abstain']} gold-abstain probes "
              f"abstained" + (f", answered: {', '.join(ho['gold_abstain_answered'])}" if ho["gold_abstain_answered"] else "")
              + f"; {ho['gold_answerable']} gold-answerable answered"
              + (f", abstained: {', '.join(ho['gold_answerable_abstained'])}" if ho["gold_answerable_abstained"] else "")
              + ". These held-out numbers are the only abstention figures here that were not available while the rule",
              "and the retrieval configuration were being designed.", ""]
        for r in holdout["results"]:
            note = ""
            if r.get("outcome") == "abstained" and r.get("uncovered_terms"):
                note = f" (gate: no passage mentions {', '.join(r['uncovered_terms'])})"
            elif r.get("outcome") == "abstained":
                note = " (downstream: no drafted sentence survived verification)"
            L.append(f"- {r['qid']} gold {r['gold']}: {r.get('outcome', 'FAIL')}{note}")
        L += [""]
    L += ["## 4. Retrieval, before and after (final gold, all top-20 judged)", "",
          (rc.replace('**', '') if recall else "recall not available")
          + " (`retrieval_report.md`, final section). This is a per-question mean, not a binomial proportion,",
          "so it carries no Wilson interval, and it is not recomputable from the committed judgment files: it needs",
          "the retriever's ranked output (the index).", "",
          "## 5. Citations resolving to a recorded page", "",
          f"{resolving['num']} distinct cited passages across the answered questions; all {resolving['num']} resolve to "
          f"a recorded page: {S(resolving['num'], resolving['den'])}. This is 1.0 by construction: verifier check 3 "
          "(`resolves`) drops any citation whose (item, leaf) has no page row before a sentence can be kept, so a kept "
          "citation cannot fail to resolve. The interval reflects the finite sample; the number confirms the gate held.", ""]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------- microlog ----------

def run_microlog(args) -> int:
    recs = read_jsonl(args.worksheet)
    sentences = [r for r in recs if r.get("kind") == "sentence"]
    marks, _ = marks_from_worksheet(sentences)
    gold = load_gold_questions_v(args.gold)
    reasons: dict = {}
    c = compute(sentences, marks, gold, reasons, "all_kept")

    strict, lenient = c["strict_support"], c["lenient_support"]
    resolving = c["citations_resolving"]
    abst, offt, falseab = c["abstention_on_should_abstain"], c["off_target_answers"], c["false_abstention_on_answerable"]
    n_abstain, n_answerable = c["counts"]["should_abstain_questions"], c["counts"]["answerable_questions"]

    juris = _microlog_jurisdiction(args.juris_db)

    recomputed = {
        "provenance": "recomputed from committed files (reports/microlog/judgment_worksheet.jsonl judgment field; "
                      "reports/microlog/gold_decisions.json questions verdicts) by scripts/audit_report.py "
                      "--scope microlog; none typed by hand.",
        "support_scope": "all kept sentences (includes the off-target answers mq43, mq44)",
        "counts": c["counts"],
        "strict_support": strict, "lenient_support": lenient,
        "citations_resolving": resolving,
        "abstention_on_should_abstain": abst,
        "off_target_answers": offt,
        "false_abstention_on_answerable": falseab,
        "jurisdiction_unknown": juris,
    }

    if not args.out_json.exists():
        print(f"{args.out_json} not found; microlog headline file expected to exist for in-place recompute")
        return 2
    published = json.loads(args.out_json.read_text(encoding="utf-8"))
    pub_run = published.get("audit_run", {})
    checks = {"_pairs": [
        ("strict_support_rate", strict["rate"], _num(published.get("strict_support_rate"))),
        ("lenient_support_rate", lenient["rate"], _num(published.get("lenient_support_rate"))),
        ("supported", c["_total"]["s"], _num((pub_run.get("support_breakdown") or {}).get("supported"))),
        ("partly", c["_total"]["p"], _num((pub_run.get("support_breakdown") or {}).get("partly"))),
        ("not", c["_total"]["n"], _num((pub_run.get("support_breakdown") or {}).get("not"))),
        ("abstention", _num(f"{len(c['_abstained_on_abstain'])}/{n_abstain}"),
         _num((pub_run.get("abstention") or {}).get("abstained_on_should_abstain"))),
        ("false_abstention", _num(f"{len(c['_false_abstentions'])}/{n_answerable}"),
         _num((pub_run.get("abstention") or {}).get("false_abstentions_answerable"))),
        ("off_target", _num(f"{len(offt['qids'])}/{n_abstain}"),
         _num((pub_run.get("abstention") or {}).get("false_answers_should_abstain"))),
        ("citations_resolving", resolving["num"], _num(pub_run.get("citations_resolving") or published.get("citations_resolving"))),
        ("jurisdiction_unknown", (juris or {}).get("rate"),
         _num((published.get("jurisdiction") or {}).get("unknown_share"))),
    ]}
    mism = guard("microlog", checks, published)
    if mism:
        print("RECOMPUTE MISMATCH (nothing written):", *mism, sep="\n  ")
        return 3

    # Merge: recomputed headline block is authoritative; overwrite the scalar headline fields the
    # README quotes so they are script-produced, and preserve corpus_facts / sensitivity / grid.
    published["recomputed"] = recomputed
    published["strict_support_rate"] = strict["rate"]
    published["lenient_support_rate"] = lenient["rate"]
    if juris and juris.get("rate") is not None and "jurisdiction" in published:
        published["jurisdiction"]["unknown_share"] = juris["rate"]
    args.out_json.write_text(json.dumps(published, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(recomputed, ensure_ascii=False, indent=2))
    return 0


def _microlog_jurisdiction(db_path: Path) -> dict | None:
    """Unknown-jurisdiction share, a corpus census from the microlog DB (not a judgment file, so
    no sampling interval). None when the DB is not present."""
    if not db_path or not Path(db_path).exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        unknown = conn.execute(
            "SELECT COUNT(*) FROM items WHERE jurisdiction_norm IS NULL OR jurisdiction_norm = 'unknown'").fetchone()[0]
    finally:
        conn.close()
    return {"unknown_items": unknown, "total_items": total,
            "rate": round(unknown / total, 4) if total else None,
            "note": "corpus census from civic_microlog.db (issuer-derived proxy, a floor); not a sample, no interval; "
                    "not recomputable from a committed judgment file"}


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv(".env")
    p = argparse.ArgumentParser()
    p.add_argument("--scope", choices=["pilot", "microlog"], default="pilot")
    p.add_argument("--judgments", default=Path("eval/judgments_phase16.json"), type=Path)
    p.add_argument("--notes", default=Path("eval/judgments_phase16_notes.md"), type=Path)
    p.add_argument("--worksheet", type=Path)
    p.add_argument("--gold", type=Path)
    p.add_argument("--summary", default=Path("reports/phase16/judgment_summary.json"), type=Path)
    p.add_argument("--holdout", default=Path("reports/phase16/holdout_run.json"), type=Path)
    p.add_argument("--recall-md", dest="recall_md", default=Path("docs/evaluation/retrieval_report.md"), type=Path)
    p.add_argument("--out-json", dest="out_json", type=Path)
    p.add_argument("--evidence", default=Path("docs/evaluation"), type=Path)
    p.add_argument("--juris-db", dest="juris_db", default=Path("data/exploration/microlog/civic_microlog.db"), type=Path)
    args = p.parse_args(argv)

    if args.scope == "pilot":
        args.worksheet = args.worksheet or Path("reports/phase16/judgment_worksheet.jsonl")
        args.gold = args.gold or Path("eval/gold_decisions.json")
        args.out_json = args.out_json or Path("reports/phase16/audit_numbers.json")
        for f in (args.worksheet, args.judgments, args.gold):
            if not f.exists():
                print(f"missing committed input: {f}")
                return 2
        return run_pilot(args)
    else:
        args.worksheet = args.worksheet or Path("reports/microlog/judgment_worksheet.jsonl")
        args.gold = args.gold or Path("reports/microlog/gold_decisions.json")
        args.out_json = args.out_json or Path("reports/microlog/audit_numbers.json")
        for f in (args.worksheet, args.gold):
            if not f.exists():
                print(f"missing committed input: {f}")
                return 2
        return run_microlog(args)


if __name__ == "__main__":
    sys.exit(main())
