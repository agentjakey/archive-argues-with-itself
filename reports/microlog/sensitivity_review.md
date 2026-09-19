# Microlog national scope: sensitivity pass and Gate 2 decision

Author: Jacob Ortiz. Scope: microlog_public_health (national). Read-only over the built scope; no
pilot file, gate, or database touched. This is the ethics gate microlog must pass before it is shown.

## Method

The harm-adjacent flag reuses the existing `src/archive_debugger/flags.py` unchanged. That module is
topic-agnostic: it matches its `TOPIC_SIGNALS` regexes against each served evidence row's title and
snippet, on the answer basis (rows sent to the model or cited), computed on serve and never cached.
Because it already carries the four topics this scope needs, no signal or crisis-line edit was made,
so pilot flag behavior is unchanged and no frozen file was edited. The pass below measures precision
and recall of that existing flag on microlog's own data.

Topics and crisis lines (from flags.py, unchanged):

- residential-school-health -> National Indian Residential School Crisis Line (1-866-925-4419), Hope for Wellness (1-855-242-3310)
- coerced-sterilization-indigenous -> Hope for Wellness (1-855-242-3310)
- tainted-blood-krever -> 9-8-8
- early-hiv-aids -> 9-8-8

## Precision (no benign public-health content mislabeled)

Risky-benign title controls that must not fire (the senses that dominate a public-health corpus):
instrument/milk/water sterilization, teaching/hearing/visual aids, first aid, blood donation, blood
pressure, blood supply. 11 title controls checked, 0 false positives. The word-boundary rules do the
work: bare "sterilization" is not matched (only coercion/eugenics phrasing), bare "aids" is not
matched, and "\bhiv\b" does not fire on "archives". No benign public-health content was mislabeled in
the controls.

## Recall (flag coverage on the known sensitive topics)

Precise passage-level coverage over the scope's own passages (SQLite prefilter, then the exact
flags.py regexes). This is corpus-wide coverage; at serve time the flag fires on the answer-basis
subset for a given query, not on all of these.

| topic | passages matched | distinct items |
| --- | --- | --- |
| residential-school-health | 589 | 222 |
| coerced-sterilization-indigenous | 106 | 36 |
| tainted-blood-krever | 501 | 210 |
| early-hiv-aids | 19,282 | 1,704 |

The flag has real recall on all four topics in this scope. A title-only probe found HIV firing on 82
titles and Krever on its titles, but residential-school and coerced-sterilization signal lives mostly
in passage text rather than titles; the passage-level numbers above are the honest recall measure.

## Precision-first caveats (noted, not fixed; gate tuning is P-EXP-10, post-festival)

Recall is best-effort by design, biased toward precision because a false positive on care-critical
topics is worse than a miss. A residential-school or coerced-sterilization document that never uses
the flagged phrasing is missed; a document naming only "AIDS" with no "HIV" is missed. These are
deliberate and are not changed here. Gate tuning, if any, is deferred to P-EXP-10 after the festival.

## Gate 2 decision (recorded)

A national 1960-onward public-health record holds Indigenous-identifying health content that cannot be
responsibly consulted on under CARE and OCAP before this is shown. The passage-level coverage above
confirms that content is genuinely present in this scope (residential-school health across 222 items,
coerced sterilization across 36). The decision for the festival:

- Microlog ships searchable with the sensitivity layer ON. Harm-adjacent pages carry the topic-agnostic
  contextual note and the correct crisis lines, never sanitized and never hidden.
- Indigenous-identifying health content is NOT featured: it is used in no golden question, no attract
  tile, no story, and no retrieval highlight.
- The coverage map still shows the provinces and territories exist in the record. Coverage/existence is
  permitted; featuring is not. Featuring waits for community consultation.

This decision and its exclusion criteria are recorded in the About/Gaps copy (web/src/components/pages/Gaps.tsx).

## Crisis-number verification

The names and numbers above match flags.py and the P-EXP-4 sensitivity brief exactly:
National Indian Residential School Crisis Line 1-866-925-4419; Hope for Wellness 1-855-242-3310; 9-8-8.
Re-verification against official sources the week of use is a manual step and remains mine.
