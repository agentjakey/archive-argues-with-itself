# Confirmatory test confirm-2: the reranker, pre-registered

Written and committed on 2026-11-03, before any question of this set was drafted. Nothing below may
change once the first draft exists; a change means a new set with a new name.

## The question

Does adding a reranker to the production answer pipeline put the right page in front of the writer more
often, without making answers worse? On small samples of each collection (2026-11-02), a reranker on
keyword search's top 30 found the source page in the first ten 6.9 points more often [+2.5, +11.3]. It
was not tested end to end, because production had no way to call it. Production now has the Workers AI
binding, so it can.

## The candidate (one, fixed now)

- Production as it is (answer path with evidence states, writer GLM-5.3 on Workers AI with reasoning
  low, keyword search alone), plus a reranker: `@cf/baai/bge-reranker-base` on Workers AI reorders the
  first DEPTH passages of the retrieved pool (src/archive_debugger/retrieve/rerank.py). No passage joins
  or leaves the pool; a failed reranker call keeps the search order.
- DEPTH was chosen on the validation split (140 questions), by a rule written down before any validation
  result was read: the depth among 15, 20 and 30 with the most source pages in the first ten, the
  smallest depth on a tie, and only if it beats no reranker (otherwise confirm-2 is not run). Validation,
  stub writer, production search:

  | Depth | Source page in the first ten (answerable, validation) |
  | --- | --- |
  | none | 55.4% (36/65) |
  | 15 | 61.5% (40/65) |
  | 20 | 61.5% (40/65) |
  | 30 | 63.1% (41/65) |

  Chosen: DEPTH = 30, the whole pool the search returns. These validation counts are small (65 answerable
  questions) and were used to choose; they are not evidence that the reranker helps. Reranker cost of the
  four validation runs: $0.014.
- Baseline: production as it is, without the reranker.

## The set

- Drafted by the same generator, prompts and gates as confirm-1 (audit/generator.py, generator version
  1, drafting model DeepSeek V4 Flash on Workers AI), seed 20261120.
- Only from documents never used before: every archive item cited by any benchmark draft, any item of the
  dev, validation or test splits, any v1 gold question's pages, and every item confirm-1 drew on (kept
  or rejected) is excluded before sampling. The excluded list is hashed into the lock.
- Per collection (pilot, microlog): 330 answerable questions and 18 each of wrong period, wrong
  jurisdiction, outside the collection's window, false premise and incomparable pair (should-refuse).
  No poor-OCR, conflicting or restricted items.
- Every draft is adjudicated by AI (Claude Opus 5.5, source "adjudicated-ai"), item by item, with a
  one-line reason, on the benchmark rubric's two checks (well formed; label correct). Only drafts that
  pass both enter. No human has checked them.
- Required after adjudication: at least 600 answerable and 150 should-refuse questions. If short, the
  same generator drafts more with seed 20261121 under the same exclusions and rules, until both counts
  are met; nothing else changes.
- Frozen by sha256 in config/benchmark_v2_confirm2.lock.json, committed before any answer is generated.

## The runs

- Each pipeline answers the set once (`run_benchmark.py run --split test --final` against the confirm-2
  lock; the candidate with `--rerank-depth 30`). A run stopped by a sleeping laptop or a network
  failure resumes the same run; it is never restarted from scratch or repeated.
- Deterministic measures on every question: source page in the first ten, answerable questions refused,
  should-refuse questions refused.
- Guardrail on a seeded sample: the first 100 questions, in a fixed random order of all item ids (seed
  "confirm2-guardrail:20261123"), that both pipelines answered. Same judge panel as confirm-1
  (gpt-oss-120b and DeepSeek V4 Flash, no escalation), failed judge calls retried by resuming at most
  twice, and checks still undecided adjudicated by AI (Claude Opus 5.5), blind to the pipeline, with a
  written reason each.
- Scored with `run_benchmark.py score`: paired bootstrap over questions, 2,000 resamples, seed 20261105.

## The rule (the same as confirm-1's, as amended)

Candidate minus baseline, 95% paired bootstrap intervals:

| Measure | Condition |
| --- | --- |
| Source page in the first ten passages (answerable) | must improve (point estimate above zero) |
| Answerable questions refused (false refusals) | upper bound at most +2 points |
| Should-refuse questions refused | lower bound at least -2 points |
| Sentences fully supported (guardrail, 100 questions) | the candidate is not shown worse by more than 2 points (upper bound not below -2) |
| Answers that do not answer the question (guardrail) | the candidate is not shown worse by more than 2 points (lower bound not above +2) |
| Planted-instruction and markup fixtures | must pass |

Every condition must hold for the reranker to ship. The result is published in docs/ACCURACY.md whatever
it says.

## Budget

At most $20 of paid calls for all of it (drafting, both runs, the reranker calls, judging), metered in
the audit ledger.
