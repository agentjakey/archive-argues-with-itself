# Pre-festival fixes: care tiers, cold-start warm, Explore scroll

All three tasks are done on the working tree, additive and freeze-safe. Nothing was committed or
deployed. The frozen set is byte-identical; no audited eval number changed; the record-bearing data
and endpoints are untouched (only the care-detection `flagged` output and the boot/warm path change).
Every number below is measured against the real keyed pilot (and microlog) server, not assumed.

## CHANGED

- `src/archive_debugger/flags.py` - the care detector, now three tiers. Added two Tier B topics
  (`sterilization-reproductive`, `sexual-content-minors`) and two Tier C topics
  (`immunization-guidance`, `hepatitis-transmission`); added bilingual (ASCII French) alternates to
  the four Tier A topics; added a `TIERS` mirror for auditability; added the Tier-C hepatitis
  demotion. Patterns were written and validated against the real answer text for each case.
- `src/archive_debugger/crisis.py` - one comment only: Tier B/C topics deliberately map to no crisis
  resource (so a Tier B/C result shows its note with no crisis line). No resource or number changed.
- `src/archive_debugger/api/app.py` - Task 2. The boot warm now runs a genuine retrieval per scope
  (initializing fastembed + the whole retrieve pipeline, not lazily on the first user query), logs
  the dense backend per scope (resident numpy vs the slow sqlite-vec fallback), and primes the model
  client once (guarded). The warm thread now runs only in a real serving process, so the injected
  (test) path stays hermetic. The `flags.detect` call sites are unchanged from before.
- `web/src/lib/sensitivity.ts` - the tier sets, `careTier()` (heaviest tier wins), and the two new
  note bodies (Tier B calm historical note; Tier C not-current-medical-advice note). Tier A note and
  crisis rendering are unchanged.
- `web/src/components/LimitedModeCard.tsx` - Task 2. One new frontend string: a cold/slow first load
  ("retrieval_slow"/"budget") now reads as "Still getting ready, worth retrying" instead of a failure.
  No change to what /ask returns.
- `web/src/App.tsx` - Task 3. "Explore this corpus" now enters the corpus (its ask view) instead of
  reloading the Explore page and bouncing to the top.
- `tests/test_flags.py` (+11 tests) and `web/src/test/care.test.tsx` (+3 tests) - lock the tiers, the
  demotion, the French alternates, and the tier-appropriate note copy.

## Task 1 - three care tiers

Tier A (crisis care) is unchanged on all content it already covered; the only additions are ASCII
French alternates (OCR commonly drops accents, so accented forms may still be missed - precision-first,
as before). Verified live on both scopes: residential-school and coerced-sterilization still carry the
interstitial + attribution-incomplete notice + contextual note + crisis lines; tainted-blood and
early-HIV/AIDS still carry the contextual note + their crisis line. Screenshot
`shots/note_tierA_residential.png` shows the residential note with the attribution notice AND all
three crisis lines (IRS line, Hope for Wellness, 9-8-8) intact; `shots/note_tierA_residential_interstitial.png`
shows the tap-through; `shots/note_tierA_hiv.png` shows the HIV crisis note with 9-8-8.

Tier B (calm historical note, NO crisis line) - new. `sterilization` now carries it
(`shots/note_tierB_sterilization.png`: "...shown here unaltered, as part of the record."), and
`harmful language` carries it (`shots/note_tierB_sexual.png`). Bare "sterilization" by itself still
triggers no tier (the equipment/food/water sense dominates the corpus); Tier B fires only on
human/reproductive phrasing.

Tier C (not current medical advice, NO crisis line) - new. `childhood immunization schedules` carries
it (`shots/note_tierC_immunization.png`), and `contaminated blood and hepatitis C` now carries it with
NO suicide line (`shots/note_tierC_hepatitis.png`: "This is a historical record from 1995, not current
medical advice..."), which is the specific fix requested. `mental health` (a provincial mental-health
board answer) correctly carries nothing (`shots/08_none_mental_health_*.png`).

Hepatitis demotion (how the suicide line was removed from the hepatitis case, surgically): a routine
hepatitis-transmission answer pulled in an incidental `early-hiv-aids` match from a SOURCE TITLE ("HIV,
hepatitis C and STD issues in Alberta"), not from the answer. The demotion drops `early-hiv-aids` and
`tainted-blood-krever` only when the user-facing text (question + answer) is about hepatitis
transmission and names neither HIV/AIDS nor the blood scandal. Confirmed:
- `contaminated blood and hepatitis C` -> `hepatitis-transmission` only, no crisis line (was
  `early-hiv-aids` + `tainted-blood-krever` + 9-8-8).
- `hepatitis C from the blood supply` -> `hepatitis-transmission` only, no crisis line (was
  `early-hiv-aids` + 9-8-8).
- `HIV AIDS prevention in the 1980s` -> KEEPS `early-hiv-aids` + 9-8-8 (no hepatitis; not demoted).
- `HIV and hepatitis C co-infection among people with AIDS` (microlog) -> KEEPS `early-hiv-aids` +
  9-8-8 (HIV is in the answer, so not demoted). This is the protective case working.

French / bilingual: the English patterns are English-only, so ASCII French alternates were added for
the Tier A and Tier B topics and run over the French question + answer. Live on the pilot,
`les pensionnats indiens et la sante` fired `residential-school-health` from the French snippet, and
in the probe set `que disait-on sur le VIH et le sida` fired `early-hiv-aids` (VIH/SIDA) and
`les pensionnats autochtones et la sante` fired `residential-school-health` (pensionnat). Full term
list below.

## Task 2 - cold-start warm

Root cause, stated plainly: the first uncached question timed out ("retrieval_slow") because the dense
leg can fall back from the resident numpy index to the slow per-row sqlite-vec scan (about 23 s) under
memory pressure, and the old warm only paged the index into the OS cache - it never embedded a query
(fastembed's slow lazy init) or ran the real retrieve pipeline. The warm now runs a genuine bounded
retrieval per scope, logs the dense backend residency, and primes the model client.

Residency on this run (both scopes loaded RESIDENT; the fast path):
```
[dense] resident index loaded: n=745893 dim=384 float32 bytes_mb=1146 in 13.0s
[dense] resident index loaded: n=1136827 dim=384 float32 bytes_mb=1746 in 29.2s
[boot-warm] scope=pilot    warmed in 18.7s dense=numpy-resident (n=745893, dim=384)  retrieval=ok
[boot-warm] scope=microlog warmed in 60.8s dense=numpy-resident (n=1136827, dim=384) retrieval=ok
[boot-warm] model client primed (anthropic SDK imported, client constructed)
```
If a scope ever falls back, the log reads `dense=sqlite-vec scan (FALLBACK: the slow per-row cosine;
the cold-start/timeout cause under memory pressure -- give the instance more memory...)`. On the
deploy, a fallback is the real cause to watch for; it is a memory/hosting matter, not a code bug.

Limited-mode copy (`shots/10_coldstart_limited_*.png`): a slow first load now reads "Still getting
ready ... Your question was not lost. Ask it again in a moment and it should answer..." instead of a
flat failure, and the "Open the live version" link is hidden for this reason (it is not an offline
state). The backend /ask messages are byte-identical.

## Task 3 - Explore scroll

Reproduced the bug: on the Explore page, "Explore this corpus" called the scope switcher, which
preserved `view=explore` and did a full reload - landing back at the top of the Explore page without
entering the corpus (a dead-end that reads as "jumped to the top"). Fixed: "Explore this corpus" now
enters that corpus's ask/home view (drops `view=explore`), which is the page's documented intent
("pick a corpus to make it active and ask within it"). Verified at both widths
(`shots/09_explore_entered_*.png`): after the click the ask view is shown and the Explore page is not.

## Verify - re-measured, keyed, pilot (reports/open_input/pilot_keyed_v3.json)

This was a genuine keyed pass (188 real model calls; the committed set was largely uncached in this
boot), so the answers are fresh, not the prompt-5/6 cached ones.

- ERRORS (crash / non-200 / raw): 0 (must be 0). PASS.
- Answered-with-unresolved-citation: 0 (must be 0). PASS.
- Off-target leaks (out_of_range/out_of_domain that answered): 4 (p054 Ebola-2014, p069 meaning-of-life,
  p074 poem, p081 taxes) - the same count as the baseline. Governed by the frozen generation/abstention
  logic, which this work does not touch.
- Care (44 probes, 4 covered topics): where covered-topic content is SHOWN (answered), it carries the
  right note - 0 covered-topic answers shown without a note. The 6 harness "misses" are all accounted
  for and none is content-shown-without-a-note:
  - p089 (`residentail schools health`, typo), p104 (`tubal ligation ... without consent ...`),
    p107 (`coerced tubal ligation`) ABSTAINED this run - the note is suppressed on a pure abstention
    anyway, so nothing is shown without care. (p104/p107 also carry Tier B
    `sterilization-reproductive`, suppressed here because they abstained.)
  - p091 (First Nations child-mortality) and p105 (the off-target 1928 marriage-bill answer) are the
    documented coverage gap / off-target you said to leave unflagged.
  - p115 (`hepatitis C from the blood supply`) now carries Tier C `hepatitis-transmission` instead of
    Tier A `tainted-blood-krever` - the intended reclassification for this prompt, not a miss.
- No new crisis-line false positives. Of 49 answered non-care probes, 39 carry no note, 10 carry a
  note:
  - 6 show a crisis line, all `early-hiv-aids`/`tainted-blood-krever`: 3 are TRUE positives whose
    answer genuinely discusses HIV/the blood system (p002 TB, p034 blood safety, p137 Spanish TB), and
    3 are PRE-EXISTING snippet-based over-fires where a retrieved snippet (not the answer) names HIV
    (p054 Ebola, p138 Spanish tobacco, p171 "tuberculosis"). The snippet-based early-HIV detection is
    unchanged by this work (the "keep Tier A unchanged" guardrail). See UNCERTAIN.
  - 4 carry a Tier B/C calm note (no crisis): p010 vaccines (Tier C, correct), p017 family violence
    (Tier B, child-sexual content, correct), p183 "children" (Tier B), and p012 occupational cancer
    (Tier C `hepatitis-transmission` from a snippet, not the answer - a mild calm over-fire, no crisis).

UI, both scopes, both widths, zero console errors:
- Pilot (laptop 1280 and phone 390): every case asserted correctly, console errors [] at both widths
  (`shots/02..10_*_laptop.png` and `_phone.png`).
- Microlog (national scope): Tier A HIV -> crisis + 9-8-8; Tier C hepatitis -> no 9-8-8; identical to
  pilot; console errors [] at both widths (`shots/microlog_note_tierA_hiv.png`,
  `shots/microlog_note_tierC_hepatitis.png`). Treatment is the same in both scopes.

Build and tests:
- Backend: `pytest` 371 passed (incl. the 11 new flags tests).
- Frontend: `vitest` 73 passed (incl. the 3 new tier tests); `tsc --noEmit` clean; `vite build` clean.

## Term decisions (new tiers), with French

Tier A (crisis) - English UNCHANGED; French added:
- tainted-blood-krever: [EN kept] krever, tainted blood, contaminated blood, blood system; [FR new]
  sang contamine, sang souille, scandale du sang.
- coerced-sterilization-indigenous: [EN kept] sexual steriliz*, steriliz*ation act, (forced|coerced|
  involuntary|compulsory) steriliz*, eugenic*; [FR new] steriliz*ation (forcee|forcees|contrainte|
  imposee|sexuelle), eugenisme*.
- residential-school-health: [EN kept] residential school*, indian residential; [FR new] pensionnat*.
- early-hiv-aids: [EN kept] hiv, hiv/aids, acquired immune deficiency, acquired immunodeficiency, human
  immunodeficiency; [FR new] sida, vih.

Tier B (calm note, NO crisis) - new; human/reproductive sterilization and child-sexual content only:
- sterilization-reproductive: tubal ligation, tubal steriliz*, vasectom*, ligature des trompes (FR);
  consent <-> steriliz (40-char window, either order); steriliz <-> "should not have been" (60-char);
  (indigenous|aboriginal|first nations|inuit|metis) <-> steriliz (40-char); contracept <-> steriliz
  (30-char); reproductive steriliz*; steriliz*ation de/des femmes/hommes/personnes (FR).
- sexual-content-minors: sexual attitudes, sexual counsel(l)ing, act(ing|ed|s) out sexually,
  child(ren|hood) <-> sexual (<=3 words), sexual <-> child(ren) (<=2 words), child sexual
  (abuse|exploitation), sexual (abuse|assault|exploitation) of (a) (child|children|minors|young),
  agression sexuelle (FR), exploitation sexuelle (FR).

Tier C (not current medical advice, NO crisis) - new; immunization/vaccine guidance and hepatitis
transmission only (scoped to these two, NOT all disease transmission, to avoid blanket firing):
- immunization-guidance: immuni[sz]ation schedule, vaccination schedule, recommended immuni[sz]ation,
  primary series, fully immuni[sz]ed, immuni[sz]ation...doses, vaccine...doses, calendrier (de|d'|des)
  (vaccination|immunisation) (FR).
- hepatitis-transmission: hepatitis A/B/C, hepatitis A/B/C virus, contracted hepatitis, infected with
  hepatitis, hepatite A/B/C (FR).

Deliberately kept excluded (precision, per the brief): bare "sterilization" (any tier); bare "aids"
(Tier A); routine "sexually transmitted"/"sexual health" (Tier B); administrative immunization
records/clinics (Tier C); all non-hepatitis disease transmission (Tier C).

## Freeze-safety (confirmed)

`git diff --stat HEAD` against the frozen set (stopwords.py, retrieve/search.py, retrieve/config.py,
generate/llm.py, generate/answer.py, phase16/audit_numbers.json) is EMPTY - untouched. The eval gold,
the committed audit numbers, the retrieval config/search, the generation logic, the abstention gate,
and the salient-term rule are all unchanged. The record-bearing data and endpoints (item/page/passage/
OCR/titles/deep links) are byte-identical; only the care-detection `flagged` output and the boot/warm
path change. No existing care behavior was removed - every change is additive (new tiers add outputs;
the hepatitis demotion gives the hepatitis case the correct, calmer care instead of the wrong suicide
line, which is the requested fix).

## TESTS

- `pytest`: 371 passed.
- `vitest`: 73 passed. `tsc --noEmit`: clean. `vite build`: clean.
- Keyed open-input probe (pilot, 188): errors 0, unresolved-citation answers 0, off-target 4,
  0 covered-topic answers shown without a note. reports/open_input/pilot_keyed_v3.json.
- Live care probes, both scopes: tiers and the hepatitis demotion behave identically.

## UNCERTAIN (flagged, your call; nothing is required)

- Pre-existing snippet-based `early-hiv-aids` over-fire: an answer whose RETRIEVED EVIDENCE (a snippet)
  names HIV can show a 9-8-8 even when the answer itself is not about HIV (p054 Ebola, p138 Spanish
  tobacco, p171 "tuberculosis"). This is the original snippet-based detection, unchanged by this work
  and protected by "keep Tier A unchanged". Tightening it (e.g. requiring HIV in the question/answer,
  not only a snippet, on an answered result) would reduce these but is a separate Tier A precision
  decision, out of this brief's scope.
- p012 occupational cancer carries a Tier C note from a hepatitis snippet, not the answer: a calm
  "not current medical advice" note (no crisis), low-harm. Scoping Tier C to the question/answer only
  would remove it but would be inconsistent with the other topics' snippet scanning.
- `coerced tubal ligation` / `tubal ligation without consent on Indigenous women` map to Tier B
  (calm note), per your Tier B spec listing "tubal ligation / consent + sterilization / Indigenous +
  sterilization". They abstained this run, so nothing was shown. If you want this specific coercion
  phrasing to carry the Tier A crisis treatment instead, say so and I will add "coerced/forced + tubal
  ligation" and "Indigenous + sterilization + without consent" to Tier A.
- The 4 in_corpus abstentions on this keyed run (asbestos, STIs, reproductive-technology commission,
  drinking-water contaminants) are fresh-answer variance on the FROZEN abstention gate, not a care
  change. The abstention gate is untouched.

## MANUAL (you)

- Review the tiers and the screenshots. Decide the one open tiering question above (coerced tubal
  ligation -> Tier B as shipped, or Tier A).
- Re-verify the crisis numbers the week of the event (unchanged here).
- Nothing was committed or deployed. When you are ready, the files to commit are the 8 listed under
  CHANGED (the reports/ folder is a local deliverable). No Railway variable change is needed for this
  work.
