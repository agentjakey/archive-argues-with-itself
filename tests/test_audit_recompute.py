"""The recompute reproduces every published headline number from the committed judgment and
gold files, for both scopes. Hermetic: reads only committed files, never the corpus DB or the
index. This is the check that the audit tables cannot drift from the judgments.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location("audit_report", ROOT / "scripts" / "audit_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


def test_pilot_headline_recompute_matches_published(audit):
    sentences = [r for r in audit.read_jsonl(ROOT / "reports/phase16/judgment_worksheet.jsonl")
                 if r.get("kind") == "sentence"]
    marks, _ = audit.load_marks_json(ROOT / "eval/judgments_phase16.json")
    gold = audit.load_gold_flat_v(ROOT / "eval/gold_decisions.json")
    reasons = audit.load_reasons(ROOT / "eval/judgments_phase16_notes.md")
    c = audit.compute(sentences, marks, gold, reasons, "answerable_only")

    assert (c["strict_support"]["num"], c["strict_support"]["den"]) == (166, 178)
    assert c["strict_support"]["rate"] == 0.9326
    assert (c["lenient_support"]["num"], c["lenient_support"]["den"]) == (177, 178)
    assert c["citations_resolving"]["num"] == 119 and c["citations_resolving"]["den"] == 119
    assert (c["abstention_on_should_abstain"]["num"], c["abstention_on_should_abstain"]["den"]) == (10, 15)
    assert (c["off_target_answers"]["num"], c["off_target_answers"]["den"]) == (5, 15)
    assert c["off_target_answers"]["qids"] == ["q015", "q030", "q036", "q037", "q049"]
    assert (c["false_abstention_on_answerable"]["num"], c["false_abstention_on_answerable"]["den"]) == (0, 35)


def test_microlog_headline_recompute_matches_published(audit):
    sentences = [r for r in audit.read_jsonl(ROOT / "reports/microlog/judgment_worksheet.jsonl")
                 if r.get("kind") == "sentence"]
    marks, _ = audit.marks_from_worksheet(sentences)
    gold = audit.load_gold_questions_v(ROOT / "reports/microlog/gold_decisions.json")
    c = audit.compute(sentences, marks, gold, {}, "all_kept")

    assert (c["strict_support"]["num"], c["strict_support"]["den"]) == (298, 304)
    assert c["strict_support"]["rate"] == 0.9803
    assert (c["lenient_support"]["num"], c["lenient_support"]["den"]) == (304, 304)
    assert c["citations_resolving"]["num"] == 200 and c["citations_resolving"]["den"] == 200
    assert (c["abstention_on_should_abstain"]["num"], c["abstention_on_should_abstain"]["den"]) == (5, 7)
    assert (c["off_target_answers"]["num"], c["off_target_answers"]["den"]) == (2, 7)
    assert c["off_target_answers"]["qids"] == ["mq43", "mq44"]
    assert c["false_abstention_on_answerable"]["qids"] == ["mq28"]


def test_every_rate_carries_a_wilson_interval(audit):
    sentences = [r for r in audit.read_jsonl(ROOT / "reports/phase16/judgment_worksheet.jsonl")
                 if r.get("kind") == "sentence"]
    marks, _ = audit.load_marks_json(ROOT / "eval/judgments_phase16.json")
    gold = audit.load_gold_flat_v(ROOT / "eval/gold_decisions.json")
    c = audit.compute(sentences, marks, gold, audit.load_reasons(ROOT / "eval/judgments_phase16_notes.md"),
                      "answerable_only")
    for key in ("strict_support", "lenient_support", "citations_resolving",
                "abstention_on_should_abstain", "off_target_answers", "false_abstention_on_answerable"):
        ci = c[key]["ci95"]
        assert ci is not None and len(ci) == 2 and 0.0 <= ci[0] <= ci[1] <= 1.0


def test_recall_is_parsed_from_the_committed_report_not_typed(audit):
    rec = audit.parse_final_recall(ROOT / "docs/evaluation/retrieval_report.md")
    assert rec is not None
    assert rec["recall@10"] == (0.347, 0.4581)
    assert rec["recall@20"] == (0.5928, 0.7276)
    assert rec["ndcg@10"] == (0.4174, 0.5082)
