# Gap report

What this archive cannot tell you, and what the tool does about each gap.
Numbers are copied from the named report files; derived figures show their
arithmetic.

## The record stops around 2009

Source: `reports/coverage_audit/finalist_sizing.md`.

Within `collection:governmentpublications`, public-health items by period:
1,352 dated 1990-2009, 44 dated 2010 or later, 18 dated 2015 or later. Scanned
government publications with OCR effectively end in the 2000s. The tool's
framing is "1960 to 2009"; it never claims to reach the present, and questions
about 2014-2020 topics (Ebola preparedness, cannabis guidance, vaping, COVID-19)
are among the should-abstain questions in the evaluation set.

## Almost half of the passages carry no date

Sources: `reports/phase5/normalize_report.json`, `reports/phase4/parse_report.md`.

After normalization, 993 items and 338,338 passages have no usable date;
338,338 / 745,893 passages = 45.4%. Only 36 items (9,469 passages) could be
dated from an explicit year in the title; no date is ever guessed. Undated
passages sit in their own lane on the timeline and in their own row of the
coverage grid, and the answer notes how many retrieved passages were undated.

## Dates in the metadata can disagree with the text

Source: `eval/labeling_notes.md` (Thin verdicts).

q018 rank 25 carries item-metadata year 1984 while its text is H1N1 / 2009
pandemic content dated 2010-10-22. The record was left as labeled. Phase 13
added a "later years" annotation: when a passage's text mentions years more than
one year after its item's metadata year, the evidence card says so
("mentions 2010 (item dated 1984)"). It changes no ranking and asserts nothing
about which date is right.

## Front and back matter pollute retrieval

Sources: `reports/phase13/sections_report.md`, `docs/evaluation/retrieval_report.md`.

Title pages, tables of contents, letters of transmittal, indexes and reference
lists match many queries lexically while answering nothing. A deterministic page
classifier (leaf position plus text signals; no labels, no model) marked 12,684
pages front matter and 3,823 back matter out of 448,496 pages with text. Its
first version was about 60% precise on back matter because a citation pattern
fired on years beside times and ratios in statistical tables; the second
requires a page range or an author entry with a nearby year and read 18 of 20 on
a fresh sample. Demoting front and back pages (score x 0.5, never excluded), on
its own and against the original Phase 7 gold, moved recall@20 from 0.6823 to
0.8061 and nDCG@10 from 0.4420 to 0.4852 with 1.4% of the top-20 unjudged. The
two misses in the sample were a commission chapter with footnote citations and a
recommendations page; the classifier is a heuristic and the evidence cards show
its class as a small tag.

## OCR quality is uneven

Source: `reports/phase4/parse_report.md`.

Of 745,893 passages, 6,186 are in the low OCR-quality bucket and 191,881 in the
medium bucket (proxy measure). Retrieval applies a soft down-weight by bucket
(1.0 / 0.9 / 0.75) and never excludes; the trail shows the raw excerpt, garbage
included, so the reader can see what the model saw.

## Jurisdiction and issuer are incomplete

Source: `reports/phase5/normalize_report.json`.

301 of 3,477 items (8.66%) have unknown jurisdiction; 1,836 items have an issuer
that matched no alias (805 distinct surfaces) and are kept under their cleaned
raw name; 204 have no issuer at all. Filters offer only the normalized values
and the coverage view shows an "unknown" jurisdiction row rather than hiding it.

## A filter can route around the answer

Source: `eval/labeling_notes.md` (q022 doc_type filter finding).

The Hospital for Sick Children inquiry items are classified
`doc_type_norm=royal_commission` (165 items, 68,849 passages), while q022's
filter is `doc_type=commission`, so the filter routed away from the documents.
Phase 13 added a configurable doc_type family (commission includes
royal_commission) for filtering; stored values were not rewritten. q022 remains
a should-abstain question by Jacob Ortiz's verdict.

## Housing was the proposal's example, not the pilot

Source: `reports/coverage_audit/finalist_sizing.md`.

Housing affordability yields 1,737 texts in the clean government scope and 1,747
in the curated union, below the 2,500 floor; only adding the microfiche-sourced
`microlog` collection (13,796) clears it, and that collection's OCR quality was
not verified. Public health clears the floor cleanly (3,477). The pivot is
recorded in the project's standing notes; a second topic is a new config and
manifest, not a code change.

## The abstention rule is a heuristic, and its sweep is in-sample

Source: `docs/evaluation/abstention_sweeps.md`; final sweep in
`docs/evaluation/retrieval_report.md`.

Sweep 1 of the frozen rule: 10 of 35 answerable questions would abstain and 4
of 15 should-abstain would answer. After a single, criterion-based amendment the
rule was frozen; sweep 2: 1 answerable would abstain (q007, on "risks") and 6
of 15 should-abstain would answer. The amendment was made after reading sweep 1
on these same 50 questions, so sweep 2 is in-sample and not an estimate of how
the rule behaves on new questions. On the final Phase 13 retriever the same
frozen rule reads 0 answerable would abstain and 9 of 15 should-abstain would
answer: the wider evidence pool covers more question terms, so the gate fires
less. Six probes still abstain on their out-of-window years or absent topics
(covid, 2020, vaping, 1905, 2015, 2017). Whether the nine that now pass the
gate produce a supported answer or a verified-citation abstention is decided
downstream, sentence by sentence.

## The evaluation judge is not independent of the system

Source: `eval/labeling_notes.md` (Methods).

All labels and judgments were decided by the author. To speed adjudication,
candidate labels for the Phase 13 extension and the Phase 16 support judgments
were first proposed by an assistant model and each was reviewed and decided by
the author; the same model family generates the tool's answers, so this judge is
not independent of the system. The Phase 13 retrieval table and the Phase 16
support rates should be read with that in mind.

## What the audit measured

Source: `docs/evaluation/audit_report.md`, `docs/evaluation/holdout_run.md`.

Every seed question once, configured model, final configuration; sentence
judgments by the author. Strict citation support (every claim in the cited
text) 93.3% (166 of 178 kept sentences on the 35 answerable questions); lenient
(supported or partly) 99.4% (177 of 178); the one "not" sentence inverted a
relation ("part of a series from the Centre" read as the Centre being part of a
series); the 11 "partly" sentences added a date or period, or moved an
attribution from a quoted body to the report's author. Abstention 10 of 15
in-sample; held-out 9 of 10 probes abstained and 4 of 5 answerable questions
answered; false abstentions 0 of 35 in-sample and 1 of 5 held-out (h015, on the
question word "federal", which no passage repeats). Recall@10 0.3470 -> 0.4581.
Cited passages resolving to a recorded page 119 of 119.

## Verification checks support, not relevance

Source: `docs/evaluation/audit_report.md`; `docs/evaluation/retrieval_report.md` (sweep).

In the Phase 16 audit run (every seed question once, real provider, final
configuration), the tool abstained on 10 of the 15 should-abstain questions and
answered 5 (q015, q030, q036, q037, q049). Jacob Ortiz's judgment of those five: each
is an all-supported answer to a different question than the one asked, on the
wrong period or the wrong object. Every sentence cited a real passage that was
in the evidence and resolved to a recorded page, and said what the passage said;
the passages simply did not bear on the question's period or subject. The
three structural checks and the fact-leak guard guarantee that a kept sentence
is supported by its page; nothing in the pipeline guarantees that the page is
about what was asked. The frozen thinness rule predicted 9 of these 15 would
pass the gate (`retrieval_report.md`, final sweep); five did and answered off
target, four passed the gate and then abstained downstream when no sentence
survived. False abstentions on the 35 answerable questions: 0 in the run, as
the sweep predicted.

Held out: 15 questions written after the rule and the retrieval configuration
were frozen, never used in any sweep or design decision, verdicts assigned before
the single run (`eval/holdout_questions.jsonl`, `docs/evaluation/holdout_run.md`).
9 of 10 should-abstain probes abstained; 4 of 5 answerable questions answered.
These are the only abstention figures that were not available while the rule
was designed. The two misses, recorded after that single run with no rule
changed:

- **h009, "What did reports say about injuries from electric scooters?"
  answered.** The gate covers a term if any retrieved passage contains it, and
  "scooters" is covered: the two kept sentences cite an undated child-safety
  pamphlet ("tricycles, carts, wagons and scooters are very dangerous under a
  child's care") and a 1988 occupational-health report ("steering on scooters
  needs adjusting" under equipment maintenance). The lexical gate cannot
  separate electric scooters from toy or workplace scooters, and every sentence
  is supported by its page. Same class as the five in-sample off-target answers:
  verification checks support, not relevance.
- **h015, "What did federal reports say about the mass influenza vaccination
  program announced in 1976?" abstained at the gate.** "federal" is a salient
  term under the frozen rule and no retrieved passage contains the word; the
  passages that describe the program refer to the federal government by other
  names. The frozen stoplist's actor-noun criterion holds "government",
  "department", "ministry" and "agency" but not "federal" (nor "provincial").
  "federal" is the first candidate for a v2 stoplist, if one is ever opened; the
  v1 rule stands unchanged, and this false abstention counts against it.

## British Columbia is not a second scope on this archive

Source: `reports/bc_audit/bc_sizing.md`.

Applying the Week 1 method to British Columbia: texts whose publisher or
creator names British Columbia yield 590 public-health items, 278 of them dated
1960-2009, against the 2,500 floor (OCR present on 25 of 25 sampled). Only 1 of
30 sampled BC health texts sits in `collection:governmentpublications`, the
Canadian-government portal the pilot uses; the rest sit in medical-heritage and
medical-library collections (Wellcome, McGill/Osler, UK MHL) and microfiche.
BC government health publishing on the Internet Archive lives in library and
microfiche collections, not the government portal, and it is an order of
magnitude short of the floor in the window.

## Pooled labels favour the retriever that was pooled

Source: `docs/evaluation/retrieval_report.md`.

Phase 7 gold was pooled from the baseline retriever's top-30, so it could not
credit passages the baseline never surfaced; the Phase 13 candidate's top-20 was
then labeled in full. On the final gold the baseline's recall@20 reads 0.5928
against its original 0.6823, not because it got worse but because relevant
passages now exist that it does not retrieve. A third retriever would surface
new unjudged passages again; `unjudged@k` is reported beside every number so
that bias stays visible.
