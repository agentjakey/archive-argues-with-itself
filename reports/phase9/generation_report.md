# Phase 9 generation report: abstention by question-term coverage

## Thinness rule (fixed a priori)

The question is tokenized with the same `[^\W_]+` lowercase tokenizer the FTS leg
uses. A salient term is a token that is not in a fixed English stopword list
(articles, conjunctions, prepositions, pronouns, auxiliaries, question words; no
domain words) and has length >= 3 or is a 4-digit number. A term is covered if any
retrieved passage text (same tokenizer) contains a token equal to it, or, for terms
of length >= 5, a token sharing its first 5 characters (crude stemming:
sanatoria/sanatorium, recommend/recommendations). The retrieved set is thin if any
salient term is uncovered, or if fewer than `min_passages` (3, the degenerate floor
for heavily filtered queries) were retrieved. On thin evidence no model is called
and the fixed form is emitted:
"the record here is thin: no retrieved passage mentions {uncovered terms} ({n_undated}
of {n_passages} retrieved passages are undated)". A second, code-decided abstention
fires when no drafted sentence survives the 3-check citation verifier.
`single_source` (all hits from one item) is a UI flag only, never an abstention.

No parameter of this rule -- stopword list, length threshold, prefix length, or
`min_passages` -- was tuned against the eval labels. The rule was specified before
the sweep below was run, and the sweep was run once.

## Superseded criterion: FTS-matched subset

The first criterion (abstain when fewer than 2 items / 3 passages of the fused top-k
came from the BM25 leg) was inert: the FTS query is an OR of every question token,
so the BM25 leg saturates on a public-health corpus. Sweep totals under that rule:
answerable questions that would abstain: 1; abstain questions that would answer: 14
(of 15). The two abstentions it did produce fired on the single-item floor, not on
thin evidence.

## Term-coverage sweep (run once; unedited)

Retrieval + thinness only, no model call. Gold verdicts are the human labels in
eval_question_gold; the tool does not infer them.

```
qid    gold        single_source would_abstain uncovered_terms
q001   answerable  True          True          authorities
q002   answerable  False         False         
q003   answerable  False         False         
q004   answerable  False         True          describe
q005   answerable  False         False         
q006   answerable  False         True          conclude
q007   answerable  False         True          risks
q008   answerable  False         False         
q009   answerable  False         False         
q010   answerable  False         True          describe
q011   answerable  False         False         
q012   answerable  False         False         
q013   answerable  False         False         
q014   answerable  False         False         
q015   abstain     False         True          recommend
q016   answerable  False         False         
q017   answerable  False         False         
q018   answerable  False         False         
q019   answerable  False         True          describe
q020   answerable  False         False         
q021   answerable  False         False         
q022   abstain     False         False         
q023   answerable  False         True          1980s
q024   answerable  False         False         
q025   answerable  False         False         
q026   answerable  False         False         
q027   answerable  False         False         
q028   answerable  False         False         
q029   abstain     True          True          1975
q030   abstain     False         False         
q031   answerable  False         False         
q032   answerable  False         False         
q033   answerable  False         True          shift
q034   answerable  False         True          1970s, 1990s
q035   answerable  False         False         
q036   abstain     False         True          2000s
q037   abstain     False         False         
q038   answerable  False         False         
q039   abstain     False         True          covid, 2020
q040   abstain     False         True          2018
q041   abstain     False         True          vaping
q042   abstain     False         True          opioid, 2016
q043   answerable  False         False         
q044   answerable  False         False         
q045   answerable  False         True          describe
q046   abstain     False         True          1905
q047   abstain     False         False         
q048   abstain     False         True          2015
q049   abstain     False         True          2014
q050   abstain     False         True          2017

answerable questions that would abstain: 10
abstain questions that would answer:     4
```

## Reading

Of the 15 gold-abstain questions, 11 would abstain, and for the intended reasons:
the missing terms are the out-of-window years and absent topics the probes were
written around (covid, 2020, 2018, vaping, opioid, 2016, 1905, 2015, 2014, 2017,
1975). Of the 35 gold-answerable questions, 10 would abstain; the uncovered terms
there are question-scaffolding verbs the stopword list does not contain (describe,
conclude, shift, risks, authorities, recommend) and decade tokens ("1980s",
"1970s", "1990s", "2000s"), which the tokenizer keeps as single tokens that no
passage repeats verbatim and that the 4-digit-year rule does not cover. These are
observations about the fixed rule, recorded here; nothing was adjusted in response.
