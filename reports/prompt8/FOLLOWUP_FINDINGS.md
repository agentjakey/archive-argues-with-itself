# Care precision follow-up: coerced tubal ligation, Indigenous-context gating, accents

Three surgical fixes inside the coerced-sterilization topic plus an accent check, all freeze-safe and
in the care layer. Nothing committed or deployed. The frozen set is byte-identical; no audited number
changed; the record-bearing data and endpoints are untouched. Every result below is measured against
the real keyed pilot/microlog server.

## Fix 1: coerced tubal ligation (and sterilization without consent) is Tier A

Coerced tubal ligation / tubes tied without consent now trigger the Tier A coerced-sterilization
treatment, not the calm Tier B note. I also generalized the "+ without consent" case from tubal
ligation to sterilization of any form (per the stated principle "coercion or consent language plus
the procedure"), because the live corpus returns coerced sterilization in non-tubal phrasings too (see
"women sterilized without their consent" below); flag this if you want it narrowed back to tubal only.

New Tier A (coerced-sterilization) patterns: forced/coerced/involuntary/compulsory/non-consensual
tubal ligation; "tubal ligation without consent"; "tubes (were) tied ... without consent"; "tying of
the (fallopian) tubes"; sterilization within 40 chars of "without (their/her/his/informed/any/proper)
consent" (either order); "non-consensual sterilization"; French "ligature des trompes forcee / sans
consentement" and "sterilisation ... sans consentement". Plain voluntary/contraceptive tubal ligation
with no coercion language keeps its Tier B mapping (no crisis line).

Before -> after:
- "coerced tubal ligation" / "tubal ligation without consent": Tier B calm note (no crisis) -> Tier A
  (interstitial + note + 9-8-8). Detection verified by unit tests; on the pilot these specific queries
  abstain on the thin record, so the note is correctly suppressed there (the care fires on the
  question only when an answer is shown).
- "women sterilized without their consent" (microlog, answered): Tier B -> Tier A
  (coerced-sterilization, 9-8-8), no attribution (no Indigenous context). Verified live.
- Plain "tubal ligation for birth control" (pilot, answered): Tier B, no crisis. Unchanged. Verified.

## Fix 2: the "about an Indigenous community" notice fires only when the record shows it

The coerced-sterilization topic is now two keys that differ only in treatment:
`coerced-sterilization` (generic: interstitial + note + 9-8-8) and `coerced-sterilization-indigenous`
(the generic topic UPGRADED when Indigenous context appears in the question, answer, or shown
evidence; it adds the attribution-incomplete notice and the Indigenous-specific lines, Hope for
Wellness and the MMIWG line). The attribution notice is a factual claim about the record, so it is
shown only where that claim is true. Residential-school content is inherently about Indigenous
communities and keeps the full treatment, always, unchanged.

Indigenous-context terms (matched accent-insensitively, only when coerced-sterilization has fired, in
English and French and including the historical terms the record uses): Indigenous, First Nations,
Metis, Inuit, Aboriginal, Native (not "native-born"), Indian, Indien/amerindien, autochtone, Premieres
Nations, treaty/treaties, Eskimo, "band council", "on reserve". Bare "band"/"reserve" are skipped
unless in those phrases.

Before -> after on the observed bug ("forced sterilisation", national scope, BC Sexual Sterilization
Act answer that never mentions Indigenous people):
- BEFORE: contextual note + attribution-incomplete notice + Hope for Wellness + MMIWG + 9-8-8 (the
  attribution notice was inaccurate there).
- AFTER (verified live, both widths): contextual note + 9-8-8 only; NO attribution notice, NO
  Indigenous-specific lines. Screenshot shots/fix2_generic_no_attribution.png.
- With Indigenous context ("sterilization without consent on First Nations women"): full treatment,
  attribution notice + Hope for Wellness + MMIWG + 9-8-8. Screenshot
  shots/fix2_indigenous_with_attribution.png. Verified live.
- "coerced sterilization of Indigenous women" (pilot): full Tier A + attribution, unchanged. Verified.
- Residential-school queries: full treatment (note + attribution + IRS line + Hope for Wellness +
  9-8-8), unchanged, both scopes. Verified.

## Fix 3: accented French matches

The care layer now normalizes the text being scanned for matching only (diacritics stripped), so the
ASCII patterns also match accented French. The DISPLAYED record is never altered - normalization
applies only to the copy being searched. Verified live on answered queries: "sante publique et le VIH
et le sida" fired early-hiv-aids, "les pensionnats indiens et la sante des enfants" fired
residential-school-health, and accented "sang contamine" fired tainted-blood-krever; the unit tests
cover accented "sterilisation forcee des Metis", "sang contamine", "Premieres Nations". (French care
queries often abstain on the thin French-specific retrieval, which is a corpus/retrieval matter
orthogonal to this fix; on an answered French query the care fires.)

## Demo-path check (pilot default landing)

Drove the four demo views and read the care note on each:
- Alberta health insurance 1974 vs 1999 compare (the featured story): NO care note. (Its two pins
  flag None; all four pilot stories flag None.)
- Page drawer on one of its scans: NO care note (the drawer renders the page image, never a care note).
- "See it decline" refusal (COVID-2020): NO care note (abstention; the note is suppressed). Required.
- Coverage grid: NO care note.

None of the four views changed from before the three-tier pass (they are not care-topic content), so
per the brief I did NOT recapture the deck screenshots. Zero console errors.

## Verify - re-measured open-input probe (cached, pilot, reports/open_input/pilot_keyed_v4.json)

Re-ran against the cached answers (minimal spend), flags recomputed on serve with the new patterns.
- ERRORS: 0. Answered-with-unresolved-citation: 0.
- Zero covered-topic misses on shown content: the 6 harness "misses" are p089 (typo, abstained),
  p104/p107 (abstained on the thin pilot record - note suppressed), p091 (the First-Nations
  child-mortality coverage gap) and p105 (the off-target 1928 answer) which you said to leave, and
  p115 (hepatitis -> Tier C, the intended reclassification).
- No new over-firing: answered non-care probes showing a crisis line stayed at 6 vs the prior run (3
  true positives whose answer is about HIV/blood; 3 pre-existing snippet-based HIV matches, unchanged
  by this work). The only two NEW non-care flags are both calm, no-crisis notes from the accent fix
  correctly catching accented French care content (p130 a French vaccination answer -> Tier C; p132 a
  French forced-sterilization query that abstained -> suppressed).

## Freeze-safety and no care behavior removed

`git diff --stat HEAD` against the frozen set (stopwords.py, retrieve/search.py, retrieve/config.py,
generate/llm.py, generate/answer.py, phase16/audit_numbers.json) is EMPTY. The record-bearing data
and endpoints are byte-identical; only the care-detection `flagged` output and the crisis-line mapping
change. No existing care behavior was removed: coerced sterilization still gets the full crisis
treatment; the only change is that the Indigenous-SPECIFIC notice and lines are now shown only when the
record shows Indigenous context (precision), and the crisis treatment itself (interstitial, note,
9-8-8) still fires on every coerced-sterilization result.

## TESTS

- `pytest` 377 passed (incl. the new coerced-tubal / without-consent / Indigenous-gating / accented-
  French tests in tests/test_flags.py).
- `vitest` 73 passed; `tsc --noEmit` clean; `vite build` clean.
- Open-input probe (pilot, cached): errors 0, unresolved-citation 0, 0 covered-topic misses on shown
  content, answered-with-crisis unchanged.
- Live, both scopes, both widths: Fix 2 gating renders correctly; zero console errors.

## UNCERTAIN / your call

- The "+ without consent" generalization from tubal ligation to all sterilization is slightly beyond
  Fix 1's literal (tubal-only) examples. It is precise (gated on "without consent", not bare
  "consent", so a voluntary "with informed consent" discussion stays out of Tier A) and matches the
  stated principle, but say the word if you want it narrowed to tubal ligation only.
- Pre-existing snippet-based early-HIV/AIDS over-fire (a 9-8-8 on an answer whose retrieved snippet,
  not the answer, names HIV: p054/p138/p171) is unchanged by this work, as before.

## MANUAL (you)

- Review the two Fix 2 screenshots and the before/after above. Decide the one open item (the
  without-consent generalization).
- Re-verify the crisis numbers the week of the event.
- Deploy steps are in reports/prompt8/DEPLOY_STEPS_followup.md (commit message carries no attribution
  line, per your instruction). Nothing was committed or deployed.
