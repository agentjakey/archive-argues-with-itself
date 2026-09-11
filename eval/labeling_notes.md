# Evaluation labeling notes

## Labeling rule (from eval/gold_decisions.json `_meta`)

r (relevant) only if the passage text itself answers the question; title pages,
TOCs, references, contact pages, and pointers to content elsewhere are n (not
relevant); any question with at least one r is answerable.

## Result

50 questions labeled: 35 answerable, 15 should-abstain. 1,500 candidate labels
(30 per question), 340 marked relevant. Abstain set: q015, q022, q029, q030, q036,
q037, q039, q040, q041, q042, q046, q047, q048, q049, q050.

## Verdicts that differed from the advisory worksheet's proposed_answerable

- q015 a->x: retrieved candidates were front-matter / pointers, not substantive
  answers on new reproductive technologies -> abstain.
- q022 a->x: the doc_type=commission filter excludes the Sick Children inquiry
  documents, which are classified doc_type=royal_commission (see filter finding
  below); retrieved candidates do not answer -> abstain.
- q029 a->x: no retrieved candidate genuinely supports the 1975-vs-1990 tobacco
  comparison -> abstain.
- q018 x->a: substantive federal vaccination/immunization committee testimony was
  present -> answerable.
- q021 x->a: substantive Alberta environmental-health reports were present ->
  answerable.
- q031 x->a: substantive Alberta mental-health policy material was present ->
  answerable.
- q043 x->a: the corpus contains a Canada Health Act annual report describing the
  British Columbia hospital insurance plan -> answerable despite BC not being a
  primary covered jurisdiction.
- q044 x->a: federal Royal Commission and Senate committee proceedings discuss
  Quebec hospital funding -> answerable.
- q045 x->a: retrieved candidates were judged to answer the question (29 of 30
  marked relevant) -> answerable.

## Thin verdicts (single- or few-passage support)

q007 ranks 20,29; q011 rank 27; q024 ranks 10,22; q026 rank 16; q028 rank 23;
q032 rank 8; q018 ranks 5,7,25; q021 ranks 4,7,27; q044 ranks 10,19; q043 rank 8.

Note: q018 rank 25 carries item-metadata year 1984 but its text is H1N1 / 2009
pandemic content dated 2010-10-22 (a post-window date leak under an answerable
verdict). Recorded, not changed.

## q022 doc_type filter finding

The "Hospital for Sick Children" inquiry items are classified
doc_type_norm=royal_commission (165 items, 68,849 passages; the only other
"sick children"-titled item is doc_type=other). q022's filter is
doc_type=commission, so the filter routes away from the actual Sick Children
documents. The filter was left unchanged; this is consistent with the abstain
verdict.

## Methods

Gold labels were assigned by Jake by reviewing the retrieval worksheet excerpts
and deciding relevance per candidate and answerable/abstain per question; they are
human-reviewed judgments, not authored from scratch.
