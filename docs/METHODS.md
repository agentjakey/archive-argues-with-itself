# Methods

How the tool was built and measured, for a reader who was not in the room.
Every number below is copied from a report in this repository and names the
file it came from; nothing is restated from memory. Where a figure is derived
from two reported numbers, the arithmetic is shown.

## 1. Choosing the corpus (Week 1 audit)

Source: `reports/coverage_audit/discovery.md`, `reports/coverage_audit/finalist_sizing.md`.

The proposal (`docs/proposal.md`) named housing as an illustrative topic and set
a floor of 2,500 usable items for a pilot corpus. Week 1 sized three candidate
topics against the Internet Archive's Canadian-government collections using
`advancedsearch.php` counts (the scrape API returned a canned baseline under
repeated use and was not trusted):

| clause | texts items |
| --- | ---: |
| `collection:governmentpublications` (base) | 104,219 |
| curated Canadian-government union (9 collections) | 105,289 |
| base + `microlog` (microfiche-sourced) | 309,555 |

| topic | base gov | curated gov | base + microlog |
| --- | ---: | ---: | ---: |
| housing_affordability | 1,737 (no) | 1,747 (no) | 13,796 (yes) |
| immigration | 1,762 (no) | 1,762 (no) | 5,174 (yes) |
| public_health | 3,413 (yes) | 3,477 (yes) | 16,857 (yes) |

Only public health clears the floor inside a clean government scope; housing and
immigration clear it only with `microlog`, whose OCR quality was unverified. The
pilot became public health with the curated union (3,477 items), `microlog`
excluded. Recency within `governmentpublications` for public_health: 1,352
items 1990-2009, 44 items 2010+, 18 items 2015+. A 25-item OCR spot check found
100% of sampled items carried usable OCR text; 7 of 25 were undated.

## 2. Harvest, parse, normalize

Sources: `reports/phase4/parse_report.md`, `reports/phase5/normalize_report.json`,
`reports/phase8/citation_report.md`.

Harvest (the only layer that talks to the Internet Archive) cached item metadata
and existing OCR derivatives under `raw/`. Parse produced 3,477 / 3,477 items,
468,405 pages (448,496 with text), 745,893 passages, FTS rows 745,893, 1
alignment-risk item, 45 items without page numbers, 0 items with zero usable
text. OCR-quality proxy buckets: 547,826 passages high, 191,881 medium, 6,186
low.

Normalize filled dates, jurisdiction, issuer and document type without
imputation. Undated before recovery: 1,029 items / 347,807 passages; recovered
from an explicit year in the title: 36 items / 9,469 passages; undated after:
993 items / 338,338 passages. Jurisdiction: federal 1,198, ontario 1,024,
alberta 949, unknown 301 (8.66%), international 5. Document type: other 2,466,
royal_commission 351, annual_report 282, standing_committee 170,
statistical_report 156, commission 28, board_or_appeal 24. 1,075 coverage cells.

Undated share of passages = 338,338 / 745,893 = 45.4% (normalize report over
parse report). The header strip's "45%" is this figure.

Every passage resolves to a recorded leaf: passages with no resolvable page row
= 0; 352,253 passages carry a printed page label, 393,640 are leaf-only. The
page deep link has one format, `https://archive.org/details/{item_id}/page/n{leaf_index}`,
defined in one module.

## 3. Retrieval

Sources: README "Retrieval"; `reports/phase7/eval_report.md`;
`docs/evaluation/retrieval_report.md`.

BM25 over an FTS5 index and dense cosine search (384-dim
`paraphrase-multilingual-MiniLM-L12-v2`, sqlite-vec, flat and exact) fused by
Reciprocal Rank Fusion (k = 60), a soft OCR-quality down-weight, and
pre-filters on period, jurisdiction and document type. Phase 13 added five
independently switchable changes, all off by default until measured: front and
back matter demotion, stopword dropping in the FTS query, a doc_type family
filter, a per-item cap on the ranking, and a "later years" annotation. Section 6
gives the measurements.

## 4. Evaluation gold

Sources: `eval/labeling_notes.md`, `reports/phase7/eval_report.md`.

50 seed questions. The candidate pool for each was the retriever's top-30; Jacob Ortiz
labeled every candidate (r only if the passage text itself answers the
question) and gave each question a verdict: 35 answerable, 15 should-abstain;
1,500 candidate labels, 340 relevant. Metrics are pooled recall@k and nDCG@10
over the judged pool, not the corpus, plus an abstention-leakage view. Phase 7
aggregate over the 50 labeled questions:

| metric | value |
| --- | ---: |
| recall@5 | 0.1928 |
| recall@10 | 0.4083 |
| recall@20 | 0.6823 |
| nDCG@10 | 0.442 |

Leakage: every should-abstain question had 0 of 30 surfaced candidates marked
relevant.

Nine verdicts differed from the advisory worksheet's proposal and are recorded
with reasons (q015, q022, q029 to abstain; q018, q021, q031, q043, q044, q045 to
answerable). One metadata case is recorded, not corrected: q018 rank 25 carries
item-metadata year 1984 but its text is H1N1 / 2009 pandemic content dated
2010-10-22.

## 5. Citations, synthesis, abstention

Sources: `reports/phase8/citation_report.md`, `docs/evaluation/abstention_sweeps.md`.

A citation is verified by three structural checks only: the cited passage id
exists; it was in the evidence retrieved for that question; it resolves to a
recorded page. Text overlap is never used as ground truth. Five real top-1
citations (q001-q005) passed all three checks; three synthetic bad citations
(unknown id, real passage outside its retrieved set, dangling leaf) failed.

The model drafts sentences that each cite passage ids. Sentences that cite
nothing, fail verification, or mention a year or page not present in their cited
passages are dropped and listed as unsupported. If no sentence survives, the
tool abstains.

Before any model call, a code-decided abstention rule runs (fixed a priori, not
tuned on labels): tokenize the question; a salient term is a non-stopword token
of length >= 3 or a 4-digit number; a term is covered if a retrieved passage has
an equal token or (for terms of length >= 5) a token sharing its first 5
characters; abstain if any salient term is uncovered or fewer than 3 passages
were retrieved. Sweep 1 (rule as first specified, run once, unedited): 10
answerable questions would abstain, 4 of 15 should-abstain questions would
answer. The stoplist was then extended once by criterion (asking verbs and
answer-form nouns; generic actor nouns), plural stemming and year/decade
coverage were added, and the rule was frozen. Sweep 2 (after the amendment, run
once, unedited): 1 answerable would abstain (q007, "risks"), 6 of 15
should-abstain would answer. Because the amendment followed inspection of sweep
1 on these same questions, sweep 2 is in-sample and is not an out-of-sample
estimate of abstention quality.

## 6. Coverage view

Source: README "Serve"; `src/archive_debugger/api/coverage.py`.

For a question, the same salient-term rule as the abstention gate is expressed
as FTS5 queries (a prefix query where the rule allows it), and the count of
matching passages is reported per decade and per jurisdiction under the active
filters, beside the count of all passages there. These are lexical matches, not
relevance. The fixed caption on the view states three limits: post-2009 OCR is
effectively absent; 45% of passages carry no date; counts are lexical matches.

## 7. Retrieval changes, measured (Phase 13)

Sources: `docs/evaluation/retrieval_report.md`, `reports/phase13/sections_report.md`,
`eval/labeling_notes.md`, `eval/gold_extension_notes.md`.

Page classifier (deterministic, from leaf position and text signals): 448,496
pages classified, 19,909 with no text left null; front 12,684 pages / 15,016
passages; body 431,989 / 723,510; back 3,823 / 7,367. Its first version read
about 60% precision on a 20-page back-matter sample because a citation pattern
fired on years beside times and ratios in tables; the second version requires a
page range or an author entry with a nearby year and read 18 / 20.

The candidate configuration (demotion with front 0.5 / back 0.5, stopword
dropping, doc_type family filter, per-item cap 5, later-years annotation)
surfaced 315 passages in its top-20 that no human had judged. Jacob Ortiz labeled them
in two batches: 280 labels (30 relevant) with 35 left uncertain, then those 35
(6 relevant, 29 not). No earlier label or verdict changed. Gold is now 1,815
labels, 376 relevant, and every passage in the candidate's top-20 is judged.

| state | gold | recall@5 | recall@10 | recall@20 | nDCG@10 | unjudged@10 | unjudged@20 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | phase7 | 0.1928 | 0.4083 | 0.6823 | 0.4420 | 0.0000 | 0.0000 |
| candidate | phase7 | 0.2565 | 0.4352 | 0.6978 | 0.4885 | 0.2140 | 0.3150 |
| baseline | final | 0.1740 | 0.3470 | 0.5928 | 0.4174 | 0.0000 | 0.0000 |
| candidate | final | 0.2438 | 0.4581 | 0.7276 | 0.5082 | 0.0000 | 0.0000 |

The baseline's numbers fall as the gold grows because relevant passages now
exist that it does not retrieve; that is the pooled-labels bias made visible.
On the final gold the candidate leads on every metric; per answerable question
nDCG@10 rises on 20, falls on 9, is flat on 6. Losses to know about: q009
(0.40 -> 0.14), q038 (0.61 -> 0.50), q035 (0.77 -> 0.68), q034 (0.37 -> 0.29),
q008 (0.69 -> 0.61), q033 (0.20 -> 0.13). The frozen thinness sweep on the
candidate: 0 answerable would abstain, 6 of 15 should-abstain abstain, 9 would
answer; the baseline sweep still reads 1 / 6.

Disclosure, from `eval/labeling_notes.md` (Methods): All labels and judgments
were decided by the author. To speed adjudication, candidate labels for the
Phase 13 extension and the Phase 16 support judgments were first proposed by an
assistant model and each was reviewed and decided by the author; the same model
family generates the tool's answers, so this judge is not independent of the
system.

## 8. Audit of the shipped system (Phase 16)

Sources: `docs/evaluation/audit_report.md`, `docs/evaluation/holdout_run.md`,
`eval/judgments_phase16.json`, `eval/judgments_phase16_notes.md`.

Every seed question was run once through `/ask` with the configured model on the
final configuration: 40 answered, 10 abstained; 190 sentences kept, 3 drafted
sentences dropped by the verifier or the fact-leak guard. The author judged
every kept sentence against the full text of its cited passages (s = every
factual claim appears in the cited text; p = a claim, date or attribution is
added or shifted; n = the sentence misstates the passage).

| number | value |
| --- | --- |
| Citation support, strict (s only), kept sentences on the 35 answerable questions | 93.3% (166 of 178) |
| Citation support, lenient (s + p) | 99.4% (177 of 178) |
| Abstention, in-sample (15 should-abstain questions) | 10 of 15 abstained; 5 answered off target |
| False abstentions, in-sample (35 answerable) | 0 of 35 |
| Abstention, held-out (`eval/holdout_questions.jsonl`, one run) | 9 of 10 probes abstained (h009 answered); 4 of 5 answerable answered (h015 abstained at the gate on the word "federal") |
| Retrieval recall@10 on the final gold, before -> after Phase 13 | 0.3470 -> 0.4581 |
| Cited passages resolving to a recorded page | 119 of 119 (verifier check 3 guarantees it) |

The five off-target answers (q015, q030, q036, q037, q049) are all-supported
answers to a different question than the one asked, on the wrong period or the
wrong object: verification guarantees support by the page, not relevance to the
question. The 12 p and 1 n sentences are listed with the author's reason for each
in the audit report; the shifts are added dates or periods, attributions moved
from a quoted body to the report's author, and one inverted relation.

## 9. What is fixed by rule

Four standing rules bind every phase (the project's standing rules): the only network
call outside harvest is the configured LLM API; citation verification is the
three structural checks and text overlap is never reported as correctness;
citations are page-level deep links with no coordinate storage; evaluation gold
is never edited to improve a run, configuration changes are logged in
`eval_runs`, and gold extensions are additive and recorded.
