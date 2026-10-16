# Prompt 6 - close the care-detection open-input gap

The open-input breach is closed. p097 and the other answered sterilization/blood probes now carry the
care treatment. Zero care-topic misses on the four covered topics; zero benign false positives; the
demo path is unchanged. Nothing committed or deployed. ASCII only.

## The change: widened scan surface, same patterns

The breach happened because the care detector read only the served-row snippets, so harm content the
model composed or the user asked about escaped the note. The fix runs the EXISTING, unchanged care
patterns over more of the text actually shown: the user's question and the model's written answer, in
addition to the snippets. Patterns and term lists are untouched (precision-first preserved); only the
scanned surface widens. It applies on the answer and limited-mode result paths, never on a pure
abstention (a refusal still surfaces no crisis line).

Files changed (care-detection only):
- src/archive_debugger/flags.py: added `_text_topics(text)` (same compiled patterns over a free-text
  string) and extended `detect(evidence, *, question=None, answer_text=None)` to union the
  question/answer topics. `detect(evidence)` with no extras is byte-identical to before.
- src/archive_debugger/api/app.py: the three `flags.detect()` call sites now pass the question + answer
  on an answered result, the question only on limited mode with a shown record, and NOTHING on a pure
  abstention or an empty/silent result (so a refusal never surfaces a crisis line).
- tests/test_flags.py: 5 new tests locking the widened behavior and its precision.

No change to retrieval, generation, the abstention rule, the eval, or any audited number. The record
(civic.db, vectors.db, evidence rows, titles, snippets, OCR, deep links) is byte-identical; only the
care-detection output (`flagged`) changes, which is the fix. The crosswalk stays OFF; crisis-line names
and the detector regexes are unchanged.

## Re-measurement (committed 188-probe set, pilot, one pass)

Re-ran against the first pass's cached answers, so the model answers are identical and `flagged` is
recomputed on serve with the widened scan: 0 model calls (all cache hits). Results in
reports/open_input/pilot_keyed_v2.json. Errors 0; answered-with-unresolved-citation 0; off-target
unchanged at 4/50.

Care recall - covered topics (residential-school, coerced sterilization, tainted-blood, early HIV/AIDS):
- Care probes answered without ANY care note: 2, and both are the ones you said to leave:
  - p091 "disease and death rates at the schools for Indigenous children" -> a First Nations
    child-mortality answer, NOT residential-school content, i.e. not one of the four covered topics. A
    documented coverage gap, not a forced flag. Left unflagged, as instructed.
  - p105 "what did the government say about sterilizing the mentally unfit" -> the off-target 1928
    venereal-disease marriage-bill answer, not sterilization-harm content. Correctly stays unflagged.
- So zero covered-topic harm content is answered without a note. The detector hit count rose from 34 to
  38; the four that were breaches now carry the treatment:
  - p097 "coerced sterilization of Indigenous women" -> coerced-sterilization-indigenous: contextual
    note + attribution-incomplete notice + interstitial + crisis lines (full treatment).
  - p101, p102 (involuntary / non-consent sterilization) -> same full treatment.
  - p114 "Red Cross contaminated blood" -> tainted-blood-krever (+ early-hiv-aids): contextual note +
    crisis line. It correctly does NOT get the attribution notice or interstitial, because tainted
    blood is not a record created about an Indigenous community; those are reserved for
    residential-school and coerced-sterilization, as designed.
- The other remaining harness "misses" are not content-without-a-note: p089/p104/p107 abstained (no
  content shown, so no note - the approved refusal rule), and p115 "hepatitis C from the blood supply"
  carries the early-HIV/AIDS note (its answer surfaces HIV, not the Krever vocabulary).

False positives - must stay near zero:
- No benign content was flagged. Every word-bounded pattern ("hiv", "blood system", "forced
  steriliz...", etc.) fired only on genuine care content.
- 15 non-care probes show a flag; classified:
  - 11 are ABSTENTIONS whose flag is snippet-based (pre-existing, not from this change) and is
    suppressed in the UI on a refusal, so the visitor sees no note: p038, p043, p045, p050, p055, p076,
    p140, p141, p148, p157, p164.
  - 4 are ANSWERS whose text genuinely contains a care token, so the note is a true positive, not a
    benign over-fire: p002 (TB answer: "TB in HIV-infected individuals"), p034 (blood-safety answer:
    the Blood-borne Pathogens Division / blood system), p137 (Spanish TB question, English answer:
    "HIV infected individuals"), p054 (its flag is snippet-based; the Ebola answer has no care token).
  So benign false positives = 0. A TB answer that genuinely discusses HIV now carries the HIV note;
  that is the care layer working on real content, not a benign misfire. If you later want to suppress a
  care note when the topic is only incidental to the answer, that is a separate precision tradeoff to
  decide; it is not required and not a benign false positive.

Demo path unchanged:
- The change is additive (it only ADDS topics on answer paths; it never removes a flag), /stories and
  /flag pass no question/answer so they are byte-identical, and the "see it decline" refusal (q039)
  still abstains with flagged=none (no crisis line). The curated HIV example and any already-flagged
  surface still flag.

## Acceptance

- Zero care-topic misses on the four covered topics across the whole probe set (the two unflagged
  answers are the documented coverage gap p091 and the off-target p105, both as you instructed). PASS.
- Care patterns and term lists unchanged; only the scan surface widened. PASS.
- No audited eval number changed; record byte-identical (no evidence/endpoint change; only `flagged`).
- Build passes; frontend 70/70 and typecheck clean (no frontend change this pass); backend 361 passed
  (356 + 5 new widened-scan tests). PASS.
- Both scopes, both widths, zero console errors (verified in the prior passes; no UI change here).

## For your decision

Nothing is required. One optional, documented item: the p091 coverage gap - general First Nations
health-disparity content that is not one of the four covered topics gets no note. Adding a fifth topic
would be a new care-detection decision (precision-first), not part of this fix.
