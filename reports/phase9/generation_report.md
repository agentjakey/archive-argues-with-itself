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

## Amendment (made once, after sweep 1; rule frozen thereafter)

Stoplist extended by criterion, not by row: (a) verbs and nouns that describe the
act of asking or the form of the answer (describe, explain, discuss, compare,
conclude/conclusion(s), recommend/recommendation(s), report/reported, state/stated,
say/said, address/addressed, identify, shift/shifted, change/changed, evolve/evolved,
differ/differed); (b) generic actor nouns (authorities, authority, officials,
government(s), department(s), ministry, agency, agencies). No topic words were added.
Plural stemming: one trailing "s" is stripped from a term and from passage tokens
longer than 3 characters before equality and prefix comparison (risks/risk). Year
handling uses the same allowed-year set as the fact-leak guard (years in any hit's
text UNION any hit's metadata year): a 4-digit year term is covered if it is in that
set; a decade term (\d{3}0s) is covered if the verbatim token appears in any hit's
text or any allowed year falls in the decade. min_passages is unchanged.

This amendment was made once, after inspecting sweep 1's uncovered-term column, so
sweep 2's totals are IN-SAMPLE with respect to the eval questions and are not an
out-of-sample estimate of abstention quality. The rule is frozen from here.

## Sweep 2 (after amendment; run once; unedited)

```
qid    gold        single_source would_abstain uncovered_terms
q001   answerable  True          False         
q002   answerable  False         False         
q003   answerable  False         False         
q004   answerable  False         False         
q005   answerable  False         False         
q006   answerable  False         False         
q007   answerable  False         True          risks
q008   answerable  False         False         
q009   answerable  False         False         
q010   answerable  False         False         
q011   answerable  False         False         
q012   answerable  False         False         
q013   answerable  False         False         
q014   answerable  False         False         
q015   abstain     False         False         
q016   answerable  False         False         
q017   answerable  False         False         
q018   answerable  False         False         
q019   answerable  False         False         
q020   answerable  False         False         
q021   answerable  False         False         
q022   abstain     False         False         
q023   answerable  False         False         
q024   answerable  False         False         
q025   answerable  False         False         
q026   answerable  False         False         
q027   answerable  False         False         
q028   answerable  False         False         
q029   abstain     True          True          1975
q030   abstain     False         False         
q031   answerable  False         False         
q032   answerable  False         False         
q033   answerable  False         False         
q034   answerable  False         False         
q035   answerable  False         False         
q036   abstain     False         False         
q037   abstain     False         False         
q038   answerable  False         False         
q039   abstain     False         True          covid, 2020
q040   abstain     False         True          2018
q041   abstain     False         True          vaping
q042   abstain     False         True          opioid, 2016
q043   answerable  False         False         
q044   answerable  False         False         
q045   answerable  False         False         
q046   abstain     False         True          1905
q047   abstain     False         False         
q048   abstain     False         True          2015
q049   abstain     False         True          2014
q050   abstain     False         True          2017

answerable questions that would abstain: 1
abstain questions that would answer:     6
```

Reading: 9 of 15 gold-abstain questions abstain, each on an out-of-window year or
absent topic (covid, 2020, 2018, vaping, opioid, 2016, 1905, 2015, 2014, 2017,
1975). One answerable question (q007) abstains on "risks": no passage in its top 12
contains a token stemming to "risk", and a 4-letter stem is below the 5-character
prefix threshold. The six gold-abstain questions that would answer (q015, q022,
q030, q036, q037, q047) have every salient term covered; q015 and q036 moved from
abstain to answer under the amendment because "recommend" is now a stopword and
"2000s" is covered by metadata years. Recorded, not acted on; the rule is frozen.

## Live samples

Recorded live runs (provider anthropic, model claude-haiku-4-5-20251001, temperature
0.0 sent in the request body), saved by Jacob Ortiz under reports/phase9/samples/ and
reproduced here verbatim, trimmed to sentences, citations, unsupported, coverage,
and generation. The files carry a UTF-8 BOM from the PowerShell redirect.
q034.json and q034_rerun.json are byte-identical (sha256
0ac539119ac19b866a1b3e3132a3710d70952a2fc939dea3b4734a1d66c36016, 2825 bytes each),
so the second body is not repeated. Note: these runs recorded prompt_sha256 over
SYSTEM only; the hash now also covers the user-prompt template source, so later
runs will show a different value for the same prompt text.

### q001 (answered; 5 page-level citations across 6 sentences; single_source)

```json
{
  "text": "Ontario public health authorities recommended that the Government of Ontario take action on tobacco prices, public education, marketing including packaging, labelling and information disclosure, retail controls, smoke-free spaces, supports for smoking cessation, finance and infrastructure, research, monitoring and evaluation, and cost recovery litigation. The Ontario Tobacco Strategy had three overall goals: prevention, protection and cessation, specifically aiming to prevent tobacco use by non-smokers particularly children and adolescents, protect Ontarians from second-hand smoke, and help smokers quit. Ontario public health authorities recommended that tobacco prices should be raised and maintained at levels at least comparable to surrounding jurisdictions, as increasing the price of cigarettes is essential to reducing and preventing smoking among young people. The Government of Ontario should fund communities to prepare and implement community-wide education programs to support smoking prevention programs delivered through the school curriculum, with mass media messages being a critical part of effective, comprehensive tobacco control. The Government of Ontario should make all indoor public places 100% smoke-free, with facilities used for recreation by young people such as arenas, bowling alleys and shopping malls made smoke-free immediately. The Government of Ontario should ban smoking in all enclosed worksites in the province, except where such worksites contain smoking areas which are separately-enclosed and separately-ventilated to the exterior of the premises.",
  "abstained": false,
  "sentences": [
    {"text": "Ontario public health authorities recommended that the Government of Ontario take action on tobacco prices, public education, marketing including packaging, labelling and information disclosure, retail controls, smoke-free spaces, supports for smoking cessation, finance and infrastructure, research, monitoring and evaluation, and cost recovery litigation.", "cited_ids": ["31761118938901#12:1"]},
    {"text": "The Ontario Tobacco Strategy had three overall goals: prevention, protection and cessation, specifically aiming to prevent tobacco use by non-smokers particularly children and adolescents, protect Ontarians from second-hand smoke, and help smokers quit.", "cited_ids": ["31761118938901#29:0"]},
    {"text": "Ontario public health authorities recommended that tobacco prices should be raised and maintained at levels at least comparable to surrounding jurisdictions, as increasing the price of cigarettes is essential to reducing and preventing smoking among young people.", "cited_ids": ["31761118938901#34:0"]},
    {"text": "The Government of Ontario should fund communities to prepare and implement community-wide education programs to support smoking prevention programs delivered through the school curriculum, with mass media messages being a critical part of effective, comprehensive tobacco control.", "cited_ids": ["31761118938901#36:0"]},
    {"text": "The Government of Ontario should make all indoor public places 100% smoke-free, with facilities used for recreation by young people such as arenas, bowling alleys and shopping malls made smoke-free immediately.", "cited_ids": ["31761118938901#40:0"]},
    {"text": "The Government of Ontario should ban smoking in all enclosed worksites in the province, except where such worksites contain smoking areas which are separately-enclosed and separately-ventilated to the exterior of the premises.", "cited_ids": ["31761118938901#40:0"]}
  ],
  "verified_citations": [
    {"passage_id": "31761118938901#12:1", "item_id": "31761118938901", "leaf_index": 12, "printed_page": null, "deep_link": "https://archive.org/details/31761118938901/page/n12"},
    {"passage_id": "31761118938901#29:0", "item_id": "31761118938901", "leaf_index": 29, "printed_page": "10", "deep_link": "https://archive.org/details/31761118938901/page/n29"},
    {"passage_id": "31761118938901#34:0", "item_id": "31761118938901", "leaf_index": 34, "printed_page": "15", "deep_link": "https://archive.org/details/31761118938901/page/n34"},
    {"passage_id": "31761118938901#36:0", "item_id": "31761118938901", "leaf_index": 36, "printed_page": "17", "deep_link": "https://archive.org/details/31761118938901/page/n36"},
    {"passage_id": "31761118938901#40:0", "item_id": "31761118938901", "leaf_index": 40, "printed_page": "21", "deep_link": "https://archive.org/details/31761118938901/page/n40"}
  ],
  "unsupported": [],
  "coverage": {"n_items": 1, "n_passages": 12, "n_undated": 0, "periods": {"1990s": 12}, "jurisdictions": {"ontario": 12}, "salient_terms": ["ontario", "public", "health", "controlling", "tobacco", "smoking"], "uncovered_terms": [], "single_source": true},
  "generation": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "temperature": 0.0, "prompt_sha256": "e8d1accdaf13d07d49d430e41c7fd0d1decacf9480c77cc42336564f513dbbd8", "max_tokens": 2048, "top_k": 12}
}
```

### q034 (temporal comparison; answered with one cited sentence per period; one sentence dropped by the fact-leak guard)

```json
{
  "text": "In 1972, Alberta implemented a policy of premium-free health care insurance coverage for all Alberta citizens over 65. In 1998-99, Alberta Blue Cross coverage was available at no cost to Alberta seniors aged 65 and over, their spouses and dependents, and to widows and widowers aged 55 to 64 years receiving the Alberta Widows' Pension and their dependents.",
  "abstained": false,
  "sentences": [
    {"text": "In 1972, Alberta implemented a policy of premium-free health care insurance coverage for all Alberta citizens over 65.", "cited_ids": ["ableg_33398004781505#52:0"]},
    {"text": "In 1998-99, Alberta Blue Cross coverage was available at no cost to Alberta seniors aged 65 and over, their spouses and dependents, and to widows and widowers aged 55 to 64 years receiving the Alberta Widows' Pension and their dependents.", "cited_ids": ["micro_IA40243301_0385#116:0"]}
  ],
  "verified_citations": [
    {"passage_id": "ableg_33398004781505#52:0", "item_id": "ableg_33398004781505", "leaf_index": 52, "printed_page": null, "deep_link": "https://archive.org/details/ableg_33398004781505/page/n52"},
    {"passage_id": "micro_IA40243301_0385#116:0", "item_id": "micro_IA40243301_0385", "leaf_index": 116, "printed_page": null, "deep_link": "https://archive.org/details/micro_IA40243301_0385/page/n116"}
  ],
  "unsupported": [
    {"text": "The Alberta Widows' Pension Program was introduced on May 1, 1983 to assist widows and widowers of limited income who were age 55 and older but under age 65, by providing financial, housing and health care benefits similar to those received by Alberta senior citizens, including premium-free coverage under the Basic Health Services Program, Extended Health Benefits Program and Alberta Blue Cross Non-Group Membership.", "cited_ids": ["statisticalsuppl1986albe#20:0"], "reason": "mentions a year or page not in the cited passages"}
  ],
  "coverage": {"n_items": 9, "n_passages": 12, "n_undated": 0, "periods": {"1980s": 7, "1990s": 3, "1970s": 2}, "jurisdictions": {"alberta": 12}, "salient_terms": ["alberta", "health", "insurance", "coverage", "1970s", "1990s"], "uncovered_terms": [], "single_source": false},
  "generation": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "temperature": 0.0, "prompt_sha256": "e8d1accdaf13d07d49d430e41c7fd0d1decacf9480c77cc42336564f513dbbd8", "max_tokens": 2048, "top_k": 12}
}
```

q034_rerun.json: byte-identical to q034.json (see above).

### q039 (gold-abstain probe; abstained before any model call)

```json
{
  "text": "the record here is thin: no retrieved passage mentions covid, 2020 (0 of 12 retrieved passages are undated)",
  "abstained": true,
  "abstention_text": "the record here is thin: no retrieved passage mentions covid, 2020 (0 of 12 retrieved passages are undated)",
  "sentences": [],
  "verified_citations": [],
  "unsupported": [],
  "coverage": {"n_items": 4, "n_passages": 12, "n_undated": 0, "periods": {"1980s": 7, "2000s": 5}, "jurisdictions": {"federal": 7, "ontario": 5}, "salient_terms": ["public", "health", "covid", "pandemic", "2020"], "uncovered_terms": ["covid", "2020"], "single_source": false},
  "generation": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "temperature": 0.0, "prompt_sha256": "e8d1accdaf13d07d49d430e41c7fd0d1decacf9480c77cc42336564f513dbbd8", "max_tokens": 2048, "top_k": 12}
}
```
