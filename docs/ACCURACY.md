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
- The sentence intervals treat sentences as independent, but sentences cluster within answers.
  Resampling whole answers instead (a cluster bootstrap, 10,000 resamples,
  `scripts/v2/v1_intervals.py`, 2026-11-01) gives, for strict support: pilot 89.3-96.5% (178 sentences, 35
  answers), microlog 95.9-99.6% (304 sentences, 41 answers). Clustering widens the microlog interval a little and
  does not widen the pilot's, because the pilot's unsupported sentences are spread over many answers.
  Where no sentence failed (lenient support, microlog) the bootstrap cannot show any spread, so the
  Wilson interval above is the one to read.
- Small denominators (7 and 15 should-abstain questions) give wide intervals.
- These are the curated evaluation questions, not visitors' questions.

## Answers after the move to Cloudflare (2026-10)

Moving the hosting changed no answer. For every seed and story question of both collections, the
ranked list of passages retrieved under the new layout (precomputed dense matrices) is identical to
v1's (pilot 53 of 53, microlog 11 of 11), so every evaluation number above is unchanged; and every
stored answer moved to the new cache is identical to its v1 record, field for field (53 of 53). The
microlog example questions that had never been answered were answered once by the same model and
prompt, and are shown as recorded answers with their date.

## The v2 audit (2026-11)

### Who checks the checkers

The v2 audit uses AI judges from two model families. To know how far to trust them, their verdicts are
compared with reference labels on a set of items. Those reference labels come from AI adjudication:
each item was read against the full text of its page and decided check by check, with a written reason
(Claude Opus 5.5, 146 items, 2026-11-02). No human has checked those labels yet, and outside review is
planned. Nothing in this section is a human check, and nothing here should be read as one.

A check may be called AI-AUDITED only when the judge panel meets the published bar against those
labels, and when the cheaper reference labels used for the bulk of the comparison (two reference judges
agreeing) are themselves shown accurate enough: on a random sample of items (80 since 2026-11-02, drawn in
two seeded halves), the upper 95% bound of their error against the adjudicated labels must be at most
10%. As of 2026-11-02 no check is AI-AUDITED:

| Check | Panel against the best labels | Why not AI-AUDITED |
| --- | --- | --- |
| SUPPORTS | 255 items, kappa 0.844, false pass 2.1% (to 4.9%), 18 of 23 failures caught | the reference labels disagree with adjudication on 4 of the random 80 (error bound 12.2%, over 10%), and 18 of 23 failures caught is under the 80% bar |
| ANSWERS | 81 items, kappa 0.679, error 12.3% (to 21.3%) | the panel misses the bar (error and false-pass bounds) |
| IN SCOPE | 296 items, kappa 0.241, 5 of 30 failures caught | the panel misses the bar: it rarely catches an out-of-scope page |

The review guide contradicted itself on one case (a sentence that credits "United States Medicaid
reports" with words found in a Canadian Senate report): its rule said a shifted source is partly supported,
its worked example said supported. The guide now follows its rule; that case was adjudicated again under the
fixed guide, and 40 more random items were adjudicated as a fresh check. The fix removed that one
disagreement (0 of the first 40); the new 40 brought four, so the reference labels still miss the bar.

AI calibration stops here: no further label rounds are planned, and no check will be called AI-AUDITED
until outside human review of these labels exists.

What this does not say: the adjudicated labels are one AI's reading; an AI adjudicator may share blind
spots with AI judges. Until outside reviewers check them, these are AI measurements of AI judges.

### Which model writes the answers, and can an open model do it?

The v2 answer carries one of six evidence states. Candidate writers answered the same 140 validation
questions of the frozen v2 benchmark through the same prompts, retrieval and checks. Every answer was
judged by one panel of two open models from other families (gpt-oss-120b and DeepSeek V4 Flash), so no
writer was judged by its own family; that panel is not calibrated to the bar (its SUPPORTS agreement
with reference labels is kappa 0.74), so the table compares writers under one fixed judge rather than
claiming accuracy. Rates are over answers without an error; every writer had a 60-second limit; "over
20 s" is the share of writer calls slower than the production limit, which in production would show
the record without an answer.

| Writer | Licence | Where it can run | Strict SUPPORTS | ANSWERS failures | False refusals | Should-refuse refused | Over 20 s | USD per answer | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Haiku 4.5, v1 (production today) | proprietary | API only | 100% (193/193) | 9.5% (4/42) | 40.0% (32/80) | 90.0% (54/60) | 1.6% | 0.024 (worst-case estimate) | 0 |
| Claude Haiku 4.5, v2 | proprietary | API only | 98.7% (154/156) | 7.5% (3/40) | 41.3% (33/80) | 90.0% (54/60) | 0% | 0.0071 | 0 |
| Claude Haiku 5.5 (effort low), v2 | proprietary | API only | 97.5% (158/162) | 2.6% (1/39) | 46.3% (37/80) | 95.0% (57/60) | 0% | 0.0012 | 0 |
| GLM-5.3, v2, default reasoning | GLM-5.3 licence (MIT terms; a security review for model-as-a-service operators over USD 10 billion revenue) | a multi-GPU node (753B parameters) | 100% (70/70) | 4.2% (1/24) | 54.7% (29/53) | 100% (52/52) | 21.9% | 0.011 | 35 cut off |
| GLM-5.3, v2, reasoning low | same | same | 100% (167/167) | 2.4% (1/41) | 45.0% (36/80) | 96.7% (58/60) | 1.6% | 0.0082 | 0 |
| Gemma 4 26B-A4B, v2, thinking on | Apache 2.0 | one 96 GB GPU; a laptop when quantized to 4 bits | 100% (11/11) | 0% (0/6) | 77.1% (27/35) | 100% (54/54) | 96.9% | 0.0010 | 51 cut off |
| Gemma 4 26B-A4B, v2, thinking off | Apache 2.0 | same | 100% (141/141) | 7.9% (3/38) | 43.8% (35/80) | 90.0% (54/60) | 7.8% | 0.0006 | 0 |

Mistral Small 4 and Apertus 70B were not run: neither was reachable without an account this project
does not have. The open models ran on Workers AI. "Cut off" means the model's reasoning used up the
2,048-token answer limit, and the check refuses a cut-off answer.

What the table says: with their reasoning turned down, both open models keep every checked sentence
supported and refuse should-refuse questions at least as often as the production writer, at a fraction
of the cost; Gemma 4, which fits one GPU, matches the production writer on supported sentences and
should-refuse refusals. What it does not say: none of the v2 writers, open or not, refuses answerable
questions less often than v1; in paired comparisons against v1 the upper bound of the change in false
refusals is +4 to +13 points, over the 2 points the promotion rule allows. Most false refusals happen
before any writer is asked, when retrieval brings back too little; that is the retrieval half of
Phase 3.

The full table, with every writer broken down by expected evidence state, is in
[evaluation/public_ai_gap.md](evaluation/public_ai_gap.md).

### Retrieval: what reaches the writer

Most refusals of answerable questions happen before any writer is asked, when the search brings back
too little. The measure is whether the page a benchmark question was drawn from is among the first ten
passages the writer receives (judged by no one).

- On the dev split, over the whole collection, keyword search alone (BM25) put the source page in the
  first ten for 57.9% of answerable questions, against 46.3% for today's mix of keyword search and a
  small embedding model (MiniLM, which reads only the first 128 tokens of a passage).
- On smaller samples of each collection (about 39,000 passages each, 160 questions), the candidates
  compared: today's mix 64 of 160; keyword search alone 93; the bge-m3 embedding model 97 alone and 95
  mixed with keyword search; qwen3-embedding 89; keyword search with a reranker on its top 30, 104.
  Embedding numbers on samples are optimistic (fewer competing passages); keyword numbers are not.
- Storing the bge-m3 vectors in one byte per number instead of four changed none of those counts.

### The promotion test (frozen test split, run once)

The candidate, chosen on the validation split before the test was run: the v2 answer with GLM-5.3
(reasoning low) and keyword search alone. Against the production pipeline on the same 352 questions,
with a paired bootstrap (2,000 resamples):

| Measure | Production | Candidate | Difference [95%] | Rule | Result |
| --- | --- | --- | --- | --- | --- |
| Source page in the first ten | 47.2% (77/163) | 60.7% (99/163) | +13.5 [+7.0, +20.4] | must improve | met |
| Answers that do not answer the question | 15.7% (11/70) | 1.4% (1/69) | -14.3 [-23.5, -5.9] | must fall | met |
| Answerable questions refused | 43.8% (88/201) | 41.8% (84/201) | -2.0 [-7.9, +4.1] | may rise at most 2 points (upper bound) | **not met** |
| Sentences fully supported | 98.2% (217/221) | 100% (312/312) | +1.8 [0.0, +4.3] | no more than 2 points worse | met |
| Should-refuse questions refused | 87.4% (132/151) | 94.0% (142/151) | +6.6 [+0.7, +12.2] | no more than 2 points worse | met |
| Planted-instruction and markup fixtures | pass | pass | | must pass | met |

The rule was fixed before the test. One condition is not met, so production did not change on this
result; the confirmatory test below decided it.

The judges left 45 to 49% of the supported and answers checks undecided (one judge failed to reply, or
the two split), so the rows above rest on the checks both judges agreed on. On 2026-11-02 every undecided
check was adjudicated by AI (Claude Opus 5.5, with a written reason, blind to which pipeline wrote the
answer; 549 checks). Scored with every check decided, the conclusion is the same and the margins are wider:

| Measure (every check decided) | Production | Candidate | Difference [95%] |
| --- | --- | --- | --- |
| Answers that do not answer the question | 25.0% (33/132) | 7.1% (9/126) | -17.9 [-26.1, -9.9] |
| Sentences fully supported | 87.5% (364/416) | 95.6% (523/547) | +8.1 [+4.6, +11.9] |

The refusal and source-page rows do not use the judges and are unchanged.

What these numbers do not say: the judges are AI models whose agreement with the reference labels is
below the bar, and the adjudication that decided the rest is one AI's reading, not a human check. The
test questions are drafted benchmark items checked by AI, not visitors' questions. A source page outside
the first ten does not mean no other page answers the question.

### The confirmatory test (confirm-1, 2026-11-02): promoted

The frozen test missed on one condition, false refusals, with 201 answerable questions. A second, larger
set decided the same question, under a plan committed before any of its questions existed
([pre-registration](evaluation/confirm1_preregistration.md), with an amendment committed before any
result was read): the same candidate, the same rule, run once.

The set: 839 questions (628 answerable, 211 that should be refused) drafted by the same generator from
documents never used in the earlier splits (2,182 archive items excluded), each draft adjudicated by AI
(Claude Opus 5.5, with a written reason; 258 of 1,097 drafts failed and were dropped). No human has checked
these questions. Frozen by sha256 before either pipeline answered it.

Candidate minus production, all 839 questions, paired bootstrap (2,000 resamples):

| Measure | Production | Candidate | Difference [95%] | Rule | Result |
| --- | --- | --- | --- | --- | --- |
| Source page in the first ten | 54.8% (344/628) | 67.7% (425/628) | +12.9 [+9.5, +16.3] | must improve | met |
| Answerable questions refused | 47.1% (296/628) | 38.1% (239/628) | -9.1 [-12.7, -5.3] | may rise at most 2 points (upper bound) | met |
| Should-refuse questions refused | 91.0% (192/211) | 96.2% (203/211) | +5.2 [+1.4, +9.3] | no more than 2 points worse | met |
| Planted-instruction and markup fixtures | pass | pass | | must pass | met |

Supported sentences and off-target answers were checked as a guardrail on a seeded sample of 100
questions both pipelines answered (same two-judge panel; the 36 checks it left undecided adjudicated by
AI, blind to the pipeline). It fails only if the candidate is shown worse by more than 2 points:

| Guardrail (100 questions) | Production | Candidate | Difference [95%] | Result |
| --- | --- | --- | --- | --- |
| Sentences fully supported | 95.9% (of 194) | 97.9% (of 285) | +2.0 [-0.7, +5.1] | holds |
| Answers that do not answer the question | 7% | 4% | -3.0 [-9.0, +3.0] | holds |

Every condition holds, so the candidate was promoted. Since release 2026-11-02.3, production answers with the
v2 evidence states, written by GLM-5.3 (an open-weight model, reasoning low, on Cloudflare Workers AI),
from keyword search alone. Reviewed answers keep the version they were reviewed under. Cost per answer
in this test: $0.0084 against production's $0.0059; median latency 3.4 s against 2.3 s (95th percentile
14.2 s against 6.5 s).

What this does not say: the questions are drafted and AI-checked, not visitors' questions; the guardrail
is a sample of 100, so it rules out large losses, not small ones; the judges and the adjudication are AI
readings, not human checks. The frozen test's result above stands as published: on that set the false
refusal bound missed. Both sets are reported, and the decision followed the plan written before the
second one was run.

### The whole collection: shards audited before they serve (2026-11-02)

Each shard of the whole collection is audited before production serves it. Questions are drafted from a seeded random
sample of its own pages, answered by the production writer (GLM-5.3, the v2 answer, keyword search), and every cited
sentence is checked by the same two-family panel for SUPPORTS. Sentences the judges split on, or one judge did not
answer, were decided by AI adjudication with a written reason.

| Shard | Sentences | Panel decided | Strict SUPPORTS, panel only | Strict SUPPORTS, every sentence | Tier |
| --- | --- | --- | --- | --- | --- |
| Government of Canada, 1899 to 1911 | 82 | 72 | 97.2% [90.4, 99.2] | 95.1% [88.1, 98.1] | INDEXED |
| Government of Canada, 1911 to 1921 | 65 | 60 | 96.7% [88.6, 99.1] | 95.4% [87.3, 98.4] | INDEXED |
| Place not read, 1861 to 1993 | 54 | 45 | 95.6% [85.2, 98.8] | 90.7% [80.1, 96.0] | INDEXED |

Every cited passage in these audits resolved to a recorded page. What this does not say: a sample of 54 to 82 sentences
gives intervals of about plus or minus 6 to 8 points; SUPPORTS is the only check measured here (not whether answers
answer the question); the judges and the adjudication are AI; and the tier stays INDEXED until outside human review
of the labels exists.

## What comes next

Outside human review of the AI-adjudicated labels and questions, which is what any AI-AUDITED claim now
waits for; a staging trial of the reranker; and the whole collection, indexed by keyword search first.
Results will be published here with the same detail.
