# Confirmatory test confirm-1: pre-registration

Written and committed on 2026-11-02, before any question of this set was drafted. Nothing below may
change once the first draft exists; a change means a new set with a new name.

## Why a second test

The frozen test split (352 questions) was used once, on 2026-11-02, for the production pipeline and the
candidate below. The candidate met every condition of the promotion rule except false refusals, whose
95% upper bound was +4.1 points against the +2 allowed, with 201 answerable questions. A fresh, larger
set decides the same question with tighter intervals. The frozen test result stays published as it is.

## The candidate (one, fixed now)

- Answer path v2 (evidence states, gated), writer GLM-5.3 on Workers AI with reasoning effort low
  (config/writers.toml candidate glm53), keyword search alone (`[retrieve] dense_weight = 0`).
- No reranker. The reranker measured on the ablation sub-corpora does not fit the engine today: the
  engine has no rerank stage (adding one changes the frozen retrieval code) and the production engine has
  no Workers AI binding. Building and validating it would be new exploratory work, so it is left out.
- Baseline: the production pipeline (v1 answer, Claude Haiku 4.5, keyword search fused with the MiniLM
  dense leg, dense_weight 1.0).

## The set

- Drafted by the same generator, prompts and gates as the frozen benchmark (audit/generator.py, generator
  version 1, drafting model DeepSeek V4 Flash on Workers AI, corpus checks unchanged), seed 20261110.
- Only from documents never used before: every archive item cited by any benchmark draft (kept or
  rejected), any item of the dev, validation or test splits, or any v1 gold question is excluded before
  sampling. The excluded list is hashed into the lock.
- Per collection (pilot, microlog): 330 answerable questions and 18 each of wrong period, wrong
  jurisdiction, outside the collection's window, false premise and incomparable pair (should-refuse).
  No poor-OCR, conflicting or restricted items.
- Every draft is adjudicated by AI (Claude Opus 5.5, source "adjudicated-ai"), item by item, with a
  one-line reason, on the benchmark rubric's two checks (well formed; label correct). Only drafts that
  pass both enter. No human has checked them.
- Required after adjudication: at least 600 answerable and 150 should-refuse questions. If short, the
  same generator drafts more with seed 20261111 under the same exclusions and rules, until both counts
  are met; nothing else changes.
- Frozen by sha256 in config/benchmark_v2_confirm1.lock.json, committed before any answer is generated.

## The runs

- Each pipeline answers the set once (`run_benchmark.py run --split test --final` against the confirm-1
  lock). A run stopped by a sleeping laptop or a network failure resumes the same run; it is never
  restarted from scratch or repeated.
- Judged by the same non-Claude panel as the frozen test (gpt-oss-120b and DeepSeek V4 Flash, no
  escalation, no leniency review). Judge calls that failed (HTTP errors, unreadable replies) are retried
  by resuming the audit run, at most twice. Checks still undecided after that (the judges split, or one
  never answered) are adjudicated by AI (Claude Opus 5.5, source "adjudicated-ai"), blind to which
  pipeline wrote the answer, with a written reason each; those decisions fill the panel's empty finals.
- Scored with `run_benchmark.py score`: paired bootstrap over questions, 2,000 resamples, seed 20261105.

## The promotion rule (unchanged)

Candidate minus production, 95% paired bootstrap intervals:

| Measure | Condition |
| --- | --- |
| Source page in the first ten passages (answerable) | must improve (point estimate above zero) |
| Answers that do not answer the question (ANSWERS not pass) | must fall (point estimate below zero) |
| Answerable questions refused (false refusals) | upper bound at most +2 points |
| Sentences fully supported (strict SUPPORTS) | lower bound at least -2 points |
| Should-refuse questions refused | lower bound at least -2 points |
| Planted-instruction and markup fixtures | must pass (passed for this exact candidate on 2026-11-02) |

Every condition must hold. The result is published in docs/ACCURACY.md whatever it says.

## Budget

At most $20 of paid calls for all of it (drafting, both runs, judging), metered in the audit ledger.

## Amendment (2026-11-02, 16:35 UTC, before any confirm-1 result was read)

Committed while the production pipeline was still answering the set and before the candidate had started.

- The full judging of both runs is cut. The only condition the frozen test missed, false refusals, needs no judges.
  Recall, false refusals and should-refuse refusals are computed from the answers on all 839 questions.
- SUPPORTS and ANSWERS become a guardrail on a seeded sample: the first 100 questions, in a fixed random order of
  all item ids (seed "confirm1-guardrail:20261113"), that both pipelines answered. Same panel, same retries, the
  undecided checks adjudicated by AI blind to the pipeline. The guardrail fails only if the candidate is shown worse
  by more than 2 points: the 95% upper bound of the strict SUPPORTS difference below -2, or the 95% lower bound of
  the ANSWERS-failure difference above +2.
- Fallback, used only if confirm-1 misses on false refusals alone: the same bound (95% upper bound at most +2 points)
  on the false-refusal difference pooled across the frozen test and confirm-1, by a stratified paired bootstrap
  (questions resampled within each set; 2,000 resamples, seed 20261105).
