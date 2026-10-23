# Care audit + two fixes (abstention suppression, dosing Tier C)

Audited the detector against the real pipeline first, then applied only the two confirmed fixes and
left the over-fires for your confirmation. Freeze-safe and in the care layer only. Frozen set
byte-identical; no audited number changed; retrieval, generation, the abstention gate, the eval, and
the record data are untouched. Nothing committed or deployed.

## Phase 1: audit (real pipeline, no code change at this point)

Surface = which surface each base topic matched (Q question, A answer, E shown evidence). "indig" =
Indigenous context detected (drives the coerced-sterilization -> -indigenous upgrade). "Frontend
shows" is what the visitor would see after applying the interstitial/note suppression logic.

| # | Query (scope) | Outcome | Served flagged (crisis) | Surface Q / A / E (indig) | Frontend shows |
|---|---|---|---|---|---|
| 1 | coerced tubal ligation of Indigenous women (federal) | pure-abstention | sterilization-reproductive () | Q: coerced-steril, steril-repro / A: - / E: steril-repro (indig=yes) | nothing THIS run; but see Fix 1 -- the interstitial leaks on a no-answer result whenever the snippets (or a limited-mode question scan) hit an interstitial topic |
| 2 | women sterilized without their consent (federal) | answer | coerced-sterilization-indigenous, sterilization-reproductive (hope_for_wellness, mmiwg, 988) | Q: coerced-steril, steril-repro / A: coerced-steril / E: steril-repro (indig=yes) | INTERSTITIAL + Tier A note + ATTRIBUTION + crisis(hope, mmiwg, 988) -- but see Phase 3: indig came only from "native" in a snippet |
| 3 | sterilization (federal) | answer | sterilization-reproductive () | Q: - / A: steril-repro / E: steril-repro | Tier B note (calm, no crisis) -- the answer was contraceptive sterilization |
| 4 | informed consent requirements for surgery (national) | answer | early-hiv-aids (988) | Q: - / A: - / E: early-hiv-aids | Tier A note + crisis(988) -- see Phase 3: HIV came from a snippet, NOT the "without consent" rule |
| 5 | blood donor clinics in the 1970s (national) | answer | early-hiv-aids (988) | Q: - / A: early-hiv-aids / E: early-hiv-aids | Tier A note + crisis(988) -- true positive: the answer is about using blood-donor clinics for HIV testing |
| 6 | contaminated blood and hepatitis C (federal) | answer | hepatitis-transmission () | Q: tainted-blood, hep / A: hep / E: early-hiv, hep | Tier C note (no crisis) -- the hepatitis demotion working |
| 7 | what dose of acetaminophen should I give my child for a fever (federal) | answer | (none) | Q: - / A: - / E: - | nothing -- the Fix 2 gap |
| 8 | sterilization of surgical instruments in hospitals (national) | answer | (none) | Q: - / A: - / E: - | nothing -- correct (equipment sterilization) |

## Phase 2, Fix 1: suppress all care on a pure abstention

Cause: on a pure abstention the backend computed `flagged` from the shown-evidence snippets, and the
frontend suppressed the contextual note on an abstention but NOT the tap-through interstitial. So an
abstention whose nearest-evidence snippets hit an interstitial topic (residential-school or coerced
sterilization) showed the heavy tap-through -- which itself renders the note, the attribution notice,
and the crisis lines -- and then the abstention. The attribution notice in particular was asserting a
record was shown when no answer was shown.

Change (care layer on serve + the matching frontend guard):
- src/archive_debugger/api/app.py: on a pure abstention (`answered` is False), both the cache-hit and
  cache-miss paths now set `flagged = None` instead of scanning the snippets. Care fires only when an
  answer is shown. (The limited-mode / degraded path is unchanged; it shows the record by design.)
- web/src/App.tsx: the interstitial now also requires `!abstentionOnly`, matching the note's existing
  guard, so a refusal never shows the tap-through even if a flag is present.

Before -> after (verified live):
- "coerced tubal ligation of Indigenous women" (federal): was observed showing the full treatment then
  abstaining; now abstains with flagged=None and shows only the abstention (no interstitial, no note).
- "residential school deaths in 2099" (federal): BEFORE flagged=residential-school-health ->
  interstitial on the abstention; AFTER flagged=None -> only the abstention.
- "coerced sterilization eugenics board in 2099" (federal): BEFORE flagged=coerced-sterilization ->
  interstitial on the abstention; AFTER flagged=None -> only the abstention.
- UI confirmed both widths: the abstention card shows, interstitial=False, note=False, console clean.

## Phase 2, Fix 2: Tier C catches drug dosing / treatment guidance

Cause: Tier C covered immunization schedules and hepatitis transmission, but not general drug dosing,
so a dosing answer carried no note.

Change: added a Tier C topic `dosing-treatment-guidance` (src/archive_debugger/flags.py, TIERS, and
web/src/lib/sensitivity.ts TIER_C_TOPICS). It fires on a number plus a dose unit (80 mg, 5 mL), a
qualified "dose" ("standard/recommended/... dose"), "dosage", "dose of/for/form", explicit intervals
("every 6 to 8 hours", "twice daily"), or a take/give/administer instruction with a dose. It is gated
so administrative or epidemiological content (coverage rates, registries, program descriptions,
disease rates) does NOT fire; validated against those negatives before shipping.

Before -> after (verified live):
- "what dose of acetaminophen should I give my child for a fever" (federal): BEFORE no note; AFTER the
  Tier C "not current medical advice" note, no crisis line (answer: "The standard dose for children of
  acetaminophen is 80 mg per solid dose form ..."). Screenshot shots/fix_dosing_tierC.png. Both widths.
- Kept off administrative/epidemiological content: "immunization coverage rates ...", "the cancer
  registry ...", "the mental health board delivers services ...", "tuberculosis rates fell ..." do not
  fire (unit-tested).

## Phase 3: over-fires reported, NOT fixed (awaiting your confirmation)

1. "informed consent requirements for surgery" (national) fired Tier A + 9-8-8. The cause is NOT the
   "without consent" rule (coerced-sterilization did not fire). It is `early-hiv-aids` matching an
   EVIDENCE SNIPPET -- a CCDR HIV-testing-consent document ("... Consent requirements (49%) ... HIV
   ...") retrieved for "consent requirements". The answer is about surgical consent and contains no
   HIV. This is the pre-existing snippet-based early-HIV/AIDS over-fire (same class as the earlier
   p054/p138/p171): a retrieved snippet names HIV while the answer does not.
   Proposed tightening (not applied): on an ANSWERED result, require the crisis topics
   (early-hiv-aids, tainted-blood-krever) to appear in the question or the answer, not only an evidence
   snippet, before showing their crisis line -- generalizing the existing hepatitis demotion to all
   incidental snippet-only HIV/blood matches. Risk to weigh: an answer genuinely about HIV where the
   model did not repeat "HIV" but a cited snippet did would lose the crisis line; the snippet content
   stays fully searchable. I did not apply it so we do not suppress a real case without your call.

2. "sterilization" (federal) returned contraceptive-sterilization content and landed in Tier B (calm
   note, no interstitial). That is the right tier for that answer; it would escalate to Tier A with the
   interstitial only if the answer surfaced the eugenics / Sexual Sterilization Act history. No
   over-fire and no tightening needed in the care layer. If you want "sterilization" to always surface
   the eugenics history, that is a retrieval/curation choice, not care detection.

3. Additional finding -- the attribution notice over-fired on "women sterilized without their consent"
   (federal). It showed coerced-sterilization-indigenous (attribution notice + Hope for Wellness +
   MMIWG), but the only Indigenous context was the word "native" in a snippet titled "The Prevalence of
   infertility in Canada" (native-born / native population, a demographic sense, not Indigenous); the
   answer is about involuntary sterilization generally. "native" is too ambiguous for the Indigenous-
   context test.
   Proposed tightening (not applied): drop bare "native" from the Indigenous-context terms, or require
   it inside an Indigenous phrase ("native people/community/woman/band"). This is precision-first and
   low risk (the genuine terms -- Indigenous, First Nations, Metis, Inuit, Aboriginal, Indian,
   autochtone, Premieres Nations, treaty, Eskimo -- stay). Flagged, not applied, so a real coerced-
   sterilization-of-Indigenous-women case is not accidentally suppressed without your call.

## Verify

Re-ran the committed open-input probe (pilot, cached; reports/open_input/pilot_keyed_v5.json):
- ERRORS 0; answered-with-unresolved-citation 0.
- Zero covered-topic care misses on SHOWN content. Of the 10 harness "misses", 7 are abstentions
  (p088/p089/p092/p093/p103/p104/p107 -- Fix 1 correctly suppresses care where no content is shown)
  and 3 are answered: p091 (First-Nations child-mortality coverage gap), p105 (off-target 1928
  marriage-bill answer), and p115 (hepatitis -> Tier C, intended). None is a covered-topic answer shown
  without its note.
- Abstention cases now show no care treatment (the 7 above).
- Dosing now carries Tier C: p033 ("measles outbreaks", which gives dosing) picked up the Tier C note,
  plus the acetaminophen verify query.
- Tier A on real residential-school and coerced-sterilization answers unchanged: 34 of 37 answered care
  probes still fire their topic (the 3 are the documented p091/p105/p115).
- No new benign over-firing: answered non-care probes showing a crisis line stayed at 6 (same as the
  prior run); the only new flag is the Tier C dosing note (no crisis).
- Backend `pytest` 380 passed (incl. the new abstention-care and dosing tests); frontend `vitest` 73
  passed; `tsc --noEmit` clean; `vite build` clean.
- Both scopes, both widths, zero console errors.

## Freeze-safety

`git diff --stat HEAD` against the frozen set (stopwords.py, retrieve/search.py, retrieve/config.py,
generate/llm.py, generate/answer.py, phase16/audit_numbers.json) is EMPTY. The record-bearing data and
endpoints are byte-identical; only the care-detection `flagged` output and its rendering change.

## Files changed (for your commit; nothing run here)

    src/archive_debugger/api/app.py        # Fix 1: flagged=None on a pure abstention (two detect sites)
    src/archive_debugger/flags.py          # Fix 2: dosing-treatment-guidance Tier C topic + TIERS
    web/src/App.tsx                        # Fix 1: interstitial also gated on !abstentionOnly
    web/src/lib/sensitivity.ts             # Fix 2: dosing-treatment-guidance in TIER_C_TOPICS
    tests/test_api.py                      # Fix 1: abstention-shows-no-care test (+ fixture text param)
    tests/test_flags.py                    # Fix 2: dosing Tier C tests
    web/src/test/care.test.tsx             # Fix 2: Tier C partition includes dosing

Commit message carries no attribution line, matching this public repo. Over-fire fixes (Phase 3) are
NOT included; tell me which to apply.
