# Accuracy

What has been measured about the answers this tool gives, how, and what the numbers do not say.
Every figure links to the committed report it comes from.

## What was measured (v1 audit)

Each collection was audited on its own questions with the configuration that ships. The author
labeled the candidate passages and judged every kept sentence against the full text of the pages it
cites. Intervals are Wilson 95% intervals computed in code (`scripts/audit_report.py`).

**Federal pilot** (3,477 items, 745,893 passages, 1960-2009), 50 questions:

| What | Value | Source |
| --- | --- | --- |
| Citation support, strict: every claim in the sentence is in the cited page (178 kept sentences) | 93.3% (166/178, 95% CI 88.6-96.1%) | [audit report](evaluation/audit_report.md) |
| Citation support, lenient: supported or partly supported | 99.4% (177/178, 95% CI 96.9-99.9%) | [audit report](evaluation/audit_report.md) |
| Cited passages that resolve to a recorded page | 100% (119/119, 95% CI 96.9-100%) | [audit report](evaluation/audit_report.md) |
| Abstention on questions the archive cannot answer | 66.7% (10/15, 95% CI 41.7-84.8%) in-sample; 9/10 held out | [audit report](evaluation/audit_report.md), [held-out run](evaluation/holdout_run.md) |
| Off-target answers on should-abstain questions | 33.3% (5/15, 95% CI 15.2-58.3%) in-sample | [audit report](evaluation/audit_report.md) |
| False abstention on answerable questions | 0% (0/35, 95% CI 0.0-9.9%) in-sample; 1/5 held out | [held-out run](evaluation/holdout_run.md) |

**National microlog** (13,539 items, 1,136,827 passages, 1963-2018), 47 questions:

| What | Value | Source |
| --- | --- | --- |
| Citation support, strict (304 kept sentences) | 98.0% (298/304, 95% CI 95.8-99.1%) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Citation support, lenient | 100% (304/304, 95% CI 98.8-100%) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Cited passages that resolve to a recorded page | 100% (200/200, 95% CI 98.1-100%) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Abstention on should-abstain questions | 71.4% (5/7, 95% CI 35.9-91.8%) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Off-target answers on should-abstain questions | 28.6% (2/7, 95% CI 8.2-64.1%) | [audit numbers](../reports/microlog/audit_numbers.json) |
| False abstention on answerable questions | 2.5% (1/40, 95% CI 0.4-12.9%) | [audit numbers](../reports/microlog/audit_numbers.json) |

## What these numbers do not say

- The judgments are by one person, the author; no outside reviewer has checked them yet. Candidate
  labels were proposed by an assistant model of the same family that writes the answers, then
  reviewed and decided by the author.
- The pilot's abstention rule was amended once against its own 50 questions, so its abstention
  figures are in-sample; the held-out run is the exception.
- The sentence intervals treat sentences as independent, but sentences cluster within answers, so
  the true uncertainty is wider than shown. Intervals that account for this come with the next audit.
- Small denominators (7 and 15 should-abstain questions) give wide intervals.
- These are the curated evaluation questions, not visitors' questions.

## Answers after the move to Cloudflare (2026-10)

Moving the hosting changed no answer. For every seed and story question of both collections, the
ranked list of passages retrieved under the new layout (precomputed dense matrices) is identical to
v1's (pilot 53 of 53, microlog 11 of 11), so every evaluation number above is unchanged; and every
stored answer moved to the new cache is identical to its v1 record, field for field (53 of 53). The
microlog example questions that had never been answered were answered once by the same model and
prompt, and are shown as recorded answers with their date.

## What comes next

A fuller audit with judges from two model families, calibrated against human labels and spot-checked
on every release, with a frozen benchmark of answerable and should-refuse questions. Its results will
be published here with the same detail.
