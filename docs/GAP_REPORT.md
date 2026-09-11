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

Sources: `reports/phase13/sections_report.md`, `reports/phase13/retrieval_report.md`.

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
a should-abstain question by Jake's verdict.

## Housing was the proposal's example, not the pilot

Source: `reports/coverage_audit/finalist_sizing.md`.

Housing affordability yields 1,737 texts in the clean government scope and 1,747
in the curated union, below the 2,500 floor; only adding the microfiche-sourced
`microlog` collection (13,796) clears it, and that collection's OCR quality was
not verified. Public health clears the floor cleanly (3,477). The pivot is
recorded in the project's standing notes; a second topic is a new config and
manifest, not a code change.

## The abstention rule is a heuristic, and its sweep is in-sample

Source: `reports/phase9/generation_report.md`; final sweep in
`reports/phase13/retrieval_report.md`.

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

For the Phase 13 gold extension (315 passages in two batches), candidate labels
were proposed by an LLM assistant from the worksheet excerpts and each was
reviewed and decided by Jake. The same model family generates the answers. The
labels are Jake's decisions, but the proposals that framed them were not, and
the numbers in the Phase 13 table should be read with that in mind.

## Pooled labels favour the retriever that was pooled

Source: `reports/phase13/retrieval_report.md`.

Phase 7 gold was pooled from the baseline retriever's top-30, so it could not
credit passages the baseline never surfaced; the Phase 13 candidate's top-20 was
then labeled in full. On the final gold the baseline's recall@20 reads 0.5928
against its original 0.6823, not because it got worse but because relevant
passages now exist that it does not retrieve. A third retriever would surface
new unjudged passages again; `unjudged@k` is reported beside every number so
that bias stays visible.
