# Phase 7 eval report

Generated 2026-10-08 04:52 UTC.

dense backend: numpy

labeled questions: 50 / 50

Pooled values: recall/nDCG denominators are the judged top-N pool, not the corpus, so these are pooled values, not absolute recall.

## Aggregate (labeled questions only)
- recall@5: 0.2438
- recall@10: 0.4581
- recall@20: 0.7276
- ndcg@10: 0.5084
- unjudged@10: 0.0
- unjudged@20: 0.0

## Abstention leakage (should-abstain questions)

| qid | surfaced | marked relevant |
| --- | ---: | ---: |
| q015 | 30 | 0 |
| q022 | 30 | 0 |
| q029 | 30 | 0 |
| q030 | 30 | 0 |
| q036 | 30 | 2 |
| q037 | 30 | 0 |
| q039 | 30 | 0 |
| q040 | 30 | 0 |
| q041 | 30 | 0 |
| q042 | 30 | 0 |
| q046 | 30 | 0 |
| q047 | 30 | 0 |
| q048 | 30 | 0 |
| q049 | 30 | 0 |
| q050 | 30 | 0 |
