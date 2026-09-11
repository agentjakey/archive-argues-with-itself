# Phase 8 citation report

Page-level citations only (N3): no coordinate fields are stored or returned;
`items.has_word_coords` remains a capability flag.

## Single source of the deep link

`src/archive_debugger/retrieve/citation.py` defines the fixed format
`https://archive.org/details/{item_id}/page/n{leaf_index}` and `retrieve/search.py`
sources every `page_deep_link` from it. No other module constructs a page deep link
(`harvest/fetch.py` builds only the item-level `details_url`).

## Corpus counts (civic.db, read-only)

| Measure | Count |
| --- | ---: |
| passages total | 745,893 |
| passages with printed_page known | 352,253 |
| passages leaf-only (printed_page NULL) | 393,640 |
| pages total | 468,405 |
| pages with printed_page known | 189,558 |
| pages leaf-only | 278,847 |
| items total | 3,477 |
| items has_printed_page_map = true | 3,432 |
| items has_printed_page_map = false/null | 45 |
| items with at least one printed_page label | 2,111 |
| passages with no resolvable page row | 0 |

Every passage resolves to a recorded leaf; the printed label is attached when
known and is display metadata only (the deep link always keys on leaf_index).
Note that has_printed_page_map=true means the IA scandata page map was present
(3,432 items), not that the item carries printed page labels (2,111 items do).

## Alignment-risk item

`healthsafetyonjo00albe_3` (132 parsed pages vs 134 page-map leaves; map dropped
in Phase 4): 132 pages, leaf_index 0..131, printed_page NULL throughout. Resolves
page-level, e.g. passage `healthsafetyonjo00albe_3#5:0` ->
`https://archive.org/details/healthsafetyonjo00albe_3/page/n5`.

## 3-check verifier

Checks: (1) cited passage_id exists; (2) it was in the retrieved evidence for the
query; (3) it resolves to a real recorded page (valid deep link). Structural and
deterministic; no lexical or embedding overlap, no LLM.

Five real retrieval results (top-1 cited passage verified against its own
retrieved set, questions q001-q005):

| qid | cited passage | exists | in_evidence | resolves | ok |
| --- | --- | --- | --- | --- | --- |
| q001 | 31761118938901#20:0 | yes | yes | yes | pass |
| q002 | 31761115558595#6:0 | yes | yes | yes | pass |
| q003 | 1990allalbertast00gart#40:0 | yes | yes | yes | pass |
| q004 | 31761115549388#75:0 | yes | yes | yes | pass |
| q005 | annualreport2002albe_9#10:1 | yes | yes | yes | pass |

Three synthetic bad citations:

| case | exists | in_evidence | resolves | ok |
| --- | --- | --- | --- | --- |
| unknown passage_id | no | no | no | fail |
| real passage cited outside its retrieved set | yes | no | yes | fail |
| dangling leaf (constructed in-memory; civic.db has 0 such rows) | yes | yes | no | fail |
