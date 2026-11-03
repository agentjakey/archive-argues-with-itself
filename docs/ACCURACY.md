# Accuracy

What has been measured about the answers this site gives, how, and what the numbers do not say. Newest
first. Every figure comes from a committed report or a script in this repository. Intervals are 95%.

## In short

- Every cited passage resolves to a recorded page, in every audit so far.
- The current pipeline was adopted because it passed a rule fixed in advance, on 839 fresh questions.
- It still refuses many answerable questions, mostly because search brings back too little.
- The newer checks were made by AI judges and AI adjudication. No human has checked them yet, so nothing
  is called AI-audited.

## The reranker test (confirm-2, 2026-11-03)

A reranker (a second model that reorders the pages search found) is being tested against production on a
fresh set, under a plan committed before the set was drafted ([pre-registration](evaluation/confirm2_preregistration.md)).
It ships only if it passes the same rule as above. The result will be published here, whatever it says.

## The answers today: the confirmatory test (confirm-1, 2026-11-02)

The current pipeline gives every answer one of six evidence states, is written by GLM-5.3 (an
open-weight model, reasoning set low, on Cloudflare Workers AI), and finds pages by keyword search. It
replaced the earlier pipeline (Claude Haiku 4.5, keyword search mixed with a small embedding model) only
after passing a rule written down before the test
([pre-registration](evaluation/confirm1_preregistration.md), with an amendment committed before any
result was read).

The set: 839 questions (628 answerable, 211 that should be refused), drafted by a model from documents
never used before (2,182 archive items excluded), each draft checked by AI with a written reason (258 of
1,097 drafts failed and were dropped). No human has checked these questions. Frozen by sha256 before
either pipeline answered. New minus old, paired bootstrap (2,000 resamples):

| Measure | Old | New | Difference [95%] | Rule | Result |
| --- | --- | --- | --- | --- | --- |
| Source page in the first ten passages | 54.8% (344/628) | 67.7% (425/628) | +12.9 [+9.5, +16.3] | must improve | met |
| Answerable questions refused | 47.1% (296/628) | 38.1% (239/628) | -9.1 [-12.7, -5.3] | may rise at most 2 points | met |
| Should-refuse questions refused | 91.0% (192/211) | 96.2% (203/211) | +5.2 [+1.4, +9.3] | no more than 2 points worse | met |
| Planted-instruction and markup tests | pass | pass | | must pass | met |

Supported sentences and off-target answers were checked on a seeded sample of 100 questions both
pipelines answered (two AI judges; the 36 checks they left undecided were decided by AI, blind to the
pipeline). The check fails only if the new pipeline is shown worse by more than 2 points:

| Check (100 questions) | Old | New | Difference [95%] | Result |
| --- | --- | --- | --- | --- |
| Sentences fully supported | 95.9% (of 194) | 97.9% (of 285) | +2.0 [-0.7, +5.1] | holds |
| Answers that do not answer the question | 7% | 4% | -3.0 [-9.0, +3.0] | holds |

Cost per answer: $0.0084 against $0.0059; median time 3.4 s against 2.3 s (95th percentile 14.2 s
against 6.5 s).

What this does not say: the questions were drafted and checked by AI, not asked by visitors; a sample of
100 rules out large losses, not small ones; the judges and the adjudication are AI readings, not human
checks.

## The newer parts of the collection (2026-11-02)

Each newly built part is audited before the site searches it. Questions are drafted from a seeded random
sample of its own pages and answered by the production writer, and every cited sentence is checked by
two AI judges from different model families. Sentences they split on were decided by AI with a written
reason.

| Part | Sentences | Decided by the judges | Fully supported, judges only | Fully supported, every sentence | Tier |
| --- | --- | --- | --- | --- | --- |
| Government of Canada, 1899 to 1911 | 82 | 72 | 97.2% [90.4, 99.2] | 95.1% [88.1, 98.1] | INDEXED |
| Government of Canada, 1911 to 1921 | 65 | 60 | 96.7% [88.6, 99.1] | 95.4% [87.3, 98.4] | INDEXED |
| Place not read, 1861 to 1993 | 54 | 45 | 95.6% [85.2, 98.8] | 90.7% [80.1, 96.0] | INDEXED |

Every cited passage resolved to a recorded page. What this does not say: 54 to 82 sentences give
intervals of about 6 to 8 points either way; only support was measured here, not whether answers answer
the question; the checks are AI; the tier stays INDEXED (searchable, not audited by people).

## Who checks the checkers

The AI judges are measured against reference labels. Those labels come from AI adjudication: each item
read against the full text of its page and decided check by check, with a written reason (Claude Opus
5.5, 146 items, 2026-11-02). No human has checked them; outside review is planned. Nothing in this
section is a human check.

A check may be called AI-AUDITED only when the judges meet the published bar against those labels, and
the cheaper reference labels used for most of the comparison are themselves shown accurate enough (on 80
random items, the upper bound of their error must be at most 10%). No check is AI-AUDITED:

| Check | Judges against the best labels | Why not |
| --- | --- | --- |
| Supported | 255 items, kappa 0.844, false pass 2.1% (up to 4.9%), 18 of 23 failures caught | the reference labels disagree with adjudication on 4 of 80 (error bound 12.2%, over 10%), and 18 of 23 caught is under the 80% bar |
| Answers the question | 81 items, kappa 0.679, error 12.3% (up to 21.3%) | the judges miss the bar |
| In scope | 296 items, kappa 0.241, 5 of 30 failures caught | the judges rarely catch an out-of-scope page |

The review guide once contradicted itself on one case; it now follows its rule, that case was decided
again, and 40 more random items were adjudicated as a fresh check. They brought four disagreements, so
the reference labels still miss the bar. AI calibration stops here until outside human review exists.
An AI adjudicator may share blind spots with AI judges.

## Choosing the writer

Candidate writers answered the same 140 validation questions through the same prompts, search and
checks. One panel of two open models from other families (gpt-oss-120b and DeepSeek V4 Flash) judged
every answer, so no writer was judged by its own family. That panel is below the bar (agreement kappa
0.74 on support), so the table compares writers under one judge; it does not claim accuracy. "Over 20 s"
is the share of calls slower than the production limit.

| Writer | Licence | Where it can run | Fully supported | Off-target answers | Answerable refused | Should-refuse refused | Over 20 s | USD per answer | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Haiku 4.5, first version | proprietary | API only | 100% (193/193) | 9.5% (4/42) | 40.0% (32/80) | 90.0% (54/60) | 1.6% | 0.024 (worst-case estimate) | 0 |
| Claude Haiku 4.5, evidence states | proprietary | API only | 98.7% (154/156) | 7.5% (3/40) | 41.3% (33/80) | 90.0% (54/60) | 0% | 0.0071 | 0 |
| Claude Haiku 5.5 (effort low) | proprietary | API only | 97.5% (158/162) | 2.6% (1/39) | 46.3% (37/80) | 95.0% (57/60) | 0% | 0.0012 | 0 |
| GLM-5.3, default reasoning | GLM-5.3 licence (MIT terms; a security review for model-as-a-service operators over USD 10 billion revenue) | a multi-GPU node (753B parameters) | 100% (70/70) | 4.2% (1/24) | 54.7% (29/53) | 100% (52/52) | 21.9% | 0.011 | 35 cut off |
| GLM-5.3, reasoning low | same | same | 100% (167/167) | 2.4% (1/41) | 45.0% (36/80) | 96.7% (58/60) | 1.6% | 0.0082 | 0 |
| Gemma 4 26B-A4B, thinking on | Apache 2.0 | one 96 GB GPU; a laptop at 4 bits | 100% (11/11) | 0% (0/6) | 77.1% (27/35) | 100% (54/54) | 96.9% | 0.0010 | 51 cut off |
| Gemma 4 26B-A4B, thinking off | Apache 2.0 | same | 100% (141/141) | 7.9% (3/38) | 43.8% (35/80) | 90.0% (54/60) | 7.8% | 0.0006 | 0 |

Mistral Small 4 and Apertus 70B were not run: neither was reachable without an account this project
does not have. "Cut off" means the model's reasoning used up the 2,048-token limit; the checks refuse a
cut-off answer. Every writer, open or not, refuses answerable questions about as often as the first
version or more; most of those refusals happen before any writer is asked, when search brings back too
little. The full table: [evaluation/public_ai_gap.md](evaluation/public_ai_gap.md).

## Search: what reaches the writer

The measure is whether the page a test question was drawn from is among the first ten passages the writer
receives (no judge involved).

- Over the whole collection, keyword search alone put the source page in the first ten for 57.9% of
  answerable development questions, against 46.3% for the first version's mix of keyword search and a
  small embedding model (MiniLM, which reads only the first 128 tokens of a passage).
- On samples of each collection (about 39,000 passages each, 160 questions): the first version's mix 64
  of 160; keyword search alone 93; the bge-m3 embedding model 97 alone and 95 mixed with keyword search;
  qwen3-embedding 89; keyword search with a reranker on its top 30, 104. Embedding numbers on samples
  are optimistic (fewer competing passages); keyword numbers are not.
- Storing bge-m3 vectors in one byte per number instead of four changed none of those counts.

## The first test of the current pipeline (frozen test split, 2026-11-02)

The same candidate, against the earlier pipeline on 352 held-back questions, run once:

| Measure | Old | New | Difference [95%] | Rule | Result |
| --- | --- | --- | --- | --- | --- |
| Source page in the first ten | 47.2% (77/163) | 60.7% (99/163) | +13.5 [+7.0, +20.4] | must improve | met |
| Answers that do not answer the question | 15.7% (11/70) | 1.4% (1/69) | -14.3 [-23.5, -5.9] | must fall | met |
| Answerable questions refused | 43.8% (88/201) | 41.8% (84/201) | -2.0 [-7.9, +4.1] | may rise at most 2 points | **not met** |
| Sentences fully supported | 98.2% (217/221) | 100% (312/312) | +1.8 [0.0, +4.3] | no more than 2 points worse | met |
| Should-refuse questions refused | 87.4% (132/151) | 94.0% (142/151) | +6.6 [+0.7, +12.2] | no more than 2 points worse | met |
| Planted-instruction and markup tests | pass | pass | | must pass | met |

One condition was not met, so production did not change on this result; the larger confirmatory test
above decided it. The judges left 45 to 49% of support and off-target checks undecided; with every one
of them decided by AI (549 checks, blind to the pipeline), off-target answers were 25.0% against 7.1%
(-17.9 [-26.1, -9.9]) and fully supported sentences 87.5% against 95.6% (+8.1 [+4.6, +11.9]). Both
results are published; the decision followed the plan.

## The first version's hand audit (October 2026)

Each collection was audited on its own questions with the configuration that shipped. The author labelled
the candidate passages and judged every kept sentence against the full text of the pages it cites.
Wilson intervals, computed in code (`scripts/audit_report.py`).

**Federal public health** (3,477 documents, 745,893 passages, 1960 to 2009), 50 questions:

| What | Value | Source |
| --- | --- | --- |
| Sentences fully supported by the cited page (178 sentences) | 93.3% (166/178, 88.6 to 96.1) | [audit report](evaluation/audit_report.md) |
| Supported or partly supported | 99.4% (177/178, 96.9 to 99.9) | [audit report](evaluation/audit_report.md) |
| Cited passages that resolve to a recorded page | 100% (119/119, 96.9 to 100) | [audit report](evaluation/audit_report.md) |
| Refusal of questions the archive cannot answer | 66.7% (10/15, 41.7 to 84.8) in-sample; 9 of 10 held out | [audit report](evaluation/audit_report.md), [held-out run](evaluation/holdout_run.md) |
| Off-target answers on should-refuse questions | 33.3% (5/15, 15.2 to 58.3) in-sample | [audit report](evaluation/audit_report.md) |
| Answerable questions refused | 0% (0/35, 0.0 to 9.9) in-sample; 1 of 5 held out | [held-out run](evaluation/holdout_run.md) |

**National public health** (13,539 documents, 1,136,827 passages, 1963 to 2018), 47 questions:

| What | Value | Source |
| --- | --- | --- |
| Sentences fully supported (304 sentences) | 98.0% (298/304, 95.8 to 99.1) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Supported or partly supported | 100% (304/304, 98.8 to 100) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Cited passages that resolve to a recorded page | 100% (200/200, 98.1 to 100) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Refusal of should-refuse questions | 71.4% (5/7, 35.9 to 91.8) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Off-target answers on should-refuse questions | 28.6% (2/7, 8.2 to 64.1) | [audit numbers](../reports/microlog/audit_numbers.json) |
| Answerable questions refused | 2.5% (1/40, 0.4 to 12.9) | [audit numbers](../reports/microlog/audit_numbers.json) |

What these do not say: the judgments are by one person, the author, and no outside reviewer has checked
them; candidate labels were proposed by an assistant model of the same family that wrote the answers,
then decided by the author. The pilot's refusal rule was changed once against its own 50 questions, so
those refusal figures are in-sample (the held-out run is the exception). Sentences cluster within
answers; resampling whole answers (10,000 resamples, `scripts/v2/v1_intervals.py`) gives 89.3 to 96.5%
for the pilot and 95.9 to 99.6% for the national collection. Small denominators give wide intervals.
These are curated evaluation questions, not visitors' questions.

Moving the site to Cloudflare in October 2026 changed no answer: for every seed and story question the
ranked passages and every stored answer were identical before and after.

## Evaluation history

Every report, in order: [evaluation/](evaluation/). The first version's
[audit report](evaluation/audit_report.md), [held-out run](evaluation/holdout_run.md),
[retrieval report](evaluation/retrieval_report.md) and [refusal-rule sweeps](evaluation/abstention_sweeps.md);
the [writer comparison](evaluation/public_ai_gap.md); the
[confirm-1](evaluation/confirm1_preregistration.md) and [confirm-2](evaluation/confirm2_preregistration.md)
pre-registrations.

## What comes next

Outside human review of the AI-adjudicated labels and questions, which any AI-audited claim waits for;
and the rest of the collection, added part by part as it is built and checked.
