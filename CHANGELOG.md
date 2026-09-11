# Changelog

One entry per phase, in plain English, from the phase reports. Numbers are the
reports' numbers; each entry names its source.

## Week 1: coverage audit and topic choice
`reports/coverage_audit/discovery.md`, `reports/coverage_audit/finalist_sizing.md`

Sized three candidate topics against the Internet Archive's Canadian-government
collections with real `advancedsearch.php` counts. Public health was the only
topic to clear the 2,500-item floor inside a clean government scope (3,477 items
in the curated union); housing (1,747) and immigration (1,762) needed the
unverified microfiche collection. Found that scanned government publications
with OCR effectively stop around 2009 (public health: 1,352 items 1990-2009, 44
in 2010+, 18 in 2015+). Chose public health, 1960-2009.

## Phases 2-3: harvest and schema
`README.md` (Reproduce), `src/archive_debugger/harvest`, `src/archive_debugger/ingest/schema.py`

Harvested item metadata and existing OCR derivatives for 3,477 items into a
content-addressed cache, with polite paging and backoff. Defined the SQLite
schema (items, pages, passages, FTS, coverage cells, evaluation tables) with no
coordinate storage.

## Phase 4: parse
`reports/phase4/parse_report.md`

Parsed the cached OCR into 468,405 pages (448,496 with text) and 745,893
passages; FTS rows matched passages exactly; one alignment-risk item; 45 items
without page numbers. OCR-quality proxy: 547,826 high, 191,881 medium, 6,186
low.

## Phase 5: normalize
`reports/phase5/normalize_report.json`

Filled dates, jurisdiction, issuer and document type from the raw metadata
without imputation. 36 items recovered a year from an explicit title date; 993
items (338,338 passages) stayed undated. Jurisdiction: federal 1,198, ontario
1,024, alberta 949, unknown 301, international 5. 1,075 coverage cells.

## Phase 6: hybrid retrieval
`README.md` (Retrieval)

BM25 plus dense cosine search (384-dim multilingual MiniLM in sqlite-vec) fused
by Reciprocal Rank Fusion, a soft OCR down-weight, and period / jurisdiction /
document-type pre-filters. Provenance fails loud if a passage cannot be resolved
to a page.

## Phase 7: evaluation
`reports/phase7/eval_report.md`, `eval/labeling_notes.md`

50 seed questions; Jacob Ortiz labeled the top-30 candidates of each (1,500 labels, 340
relevant) and gave verdicts (35 answerable, 15 should-abstain). Pooled
recall@5/10/20 = 0.1928 / 0.4083 / 0.6823, nDCG@10 = 0.442. No abstention rate is
reported; an abstention-leakage view shows 0 relevant marks on every
should-abstain question.

## Phase 8: citations
`reports/phase8/citation_report.md`

One deep-link format, one module. Every one of 745,893 passages resolves to a
recorded leaf; 352,253 carry a printed page label. A deterministic three-check
verifier (exists, in evidence, resolves) passed five real citations and failed
three synthetic bad ones.

## Phase 9: synthesis and abstention
`reports/phase9/generation_report.md`

Cited sentences drafted by the configured model, each checked by the verifier
and a fact-leak guard; unsupported sentences are dropped and listed. A
code-decided thinness rule abstains before any model call. Sweep 1: 10
answerable would abstain / 4 should-abstain would answer; after one
criterion-based amendment (then frozen), sweep 2: 1 / 6, recorded as in-sample.
Live samples for q001, q034, q039 recorded.

## Phase 10: web app
`README.md` (Web app)

A reading-room interface: answer with page-level citation marks, abstention
card, decade timeline, evidence cards with page thumbnails, page drawer, compare
view, kiosk mode. URL is the state. Real waiting text with corpus figures from
`/health`.

## Phase 11: coverage view and answer cache
`README.md` (Serve)

`/coverage` counts lexical matches for a question's salient terms by decade and
jurisdiction under the active filters, with a fixed caption on what it cannot
tell you. Answers are cached by question, filters, model, prompt hash and
retrieval fingerprint. Numbered citations and a Sources list; boxes became
rules.

## Phase 12: deploy scaffolding
`docs/DEPLOY.md`

A Docker image that builds the web app inside it and bakes the embedding model;
data paths overridable by environment; a smoke test wired into CI over a fixture
corpus; a cache-warming script with a cost estimate. Later moved from Fly to a
Railway path where the container downloads and checksum-verifies the data files
from a GitHub release on first boot.

## Phase 13: retrieval quality
`reports/phase13/retrieval_report.md`, `reports/phase13/sections_report.md`, `eval/labeling_notes.md`

Five switchable changes measured one at a time and together: front/back-matter
demotion from a deterministic page classifier (back precision 18 / 20 after a
tightened citation pattern), stopword dropping, a doc_type family filter, a
per-item cap, and a later-years annotation. The candidate's 315 unjudged top-20
passages were labeled by Jacob Ortiz in two batches (additive; gold now 1,815 labels,
376 relevant). On the fully judged gold: baseline recall@10 0.3470 /
nDCG@10 0.4174 versus candidate 0.4581 / 0.5082. The candidate is on in config;
the correlated-judge disclosure is recorded in the labeling notes.

## Phase 14: methods and gaps as product
`docs/METHODS.md`, `docs/GAP_REPORT.md`

Methods and gap report written from the phase reports with every number cited;
"How this works", "Gaps" and "About" views added to the app; this changelog.

## Phase 15: exhibit
`docs/DEMO.md`, `config/stories.json`

Four stories (question, two pinned pages years apart, caption) on the home
screen and a kiosk attract loop (60 s idle, one story every 20 s, any touch
returns home). An offline pack of page images fetched once from archive.org and
served by the API when present, so a laptop with no internet still shows real
pages; the model is called only for questions not in the cache.

## Phase 16: audit
`reports/phase16/audit_report.md`, `reports/phase16/holdout_run.md`, `eval/judgments_phase16.json`

Every seed question answered once by the configured model on the final
configuration: 40 answered, 10 abstained, 190 kept sentences, 3 dropped by the
verifier or fact-leak guard. Every kept sentence judged by the author against the
full text of its cited passages: on the 35 answerable questions 166 supported, 11
partly, 1 not (strict 93.3%, lenient 99.4%). Abstention 10 of 15 in-sample, with
the 5 answered being supported answers to the wrong period or object; false
abstentions 0 of 35. Fifteen held-out questions written after everything was
frozen: 9 of 10 probes abstained, 4 of 5 answerable answered. Recall@10 0.3470 to
0.4581; 119 of 119 cited passages resolve to a recorded page.

## Public release 1.0.0
`README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`

README rewritten around the mission and the audit numbers; contribution guide,
code of conduct, issue and pull-request templates; disclosure wording unified;
author named throughout; phase numbering kept to reports and this changelog.

## BC scope audit
`reports/bc_audit/bc_sizing.md`

The Week 1 method applied to British Columbia as a second scope: items whose
publisher or creator names British Columbia yield 590 public-health texts, 278
of them dated 1960-2009, against the 2,500 floor; only 1 of 30 sampled BC health
texts sits in the Canadian-government portal collection the pilot uses, the
rest in medical-library and microfiche collections. Not a viable second scope
under the same floor and window.
