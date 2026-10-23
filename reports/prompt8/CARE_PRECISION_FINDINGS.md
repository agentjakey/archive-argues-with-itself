# Care precision: two tightenings (native-born, cited-basis crisis)

Applied exactly the two requested tightenings, nothing else. Care layer on serve only. Frozen set
byte-identical; no audited number changed; retrieval, generation, the abstention gate, the eval, and
the record data are untouched. Nothing committed or deployed.

## Fix A: the Indigenous-context test ignores demographic "native"

"native" now counts as Indigenous context only inside an Indigenous phrase (native people/peoples,
native community/communities, native woman/women, native band/bands, native nation/nations). Bare
"native", "native-born", and "native population" no longer count. Every other Indigenous term is
unchanged (Indigenous, First Nations, Metis, Inuit, Aboriginal, Indian, treaty, Eskimo, autochtone,
Premieres Nations).

Root cause found in the audit: the offending snippet was OCR'd as "native- born" (a space after the
hyphen), which defeated the old `native(?!-born)` guard and matched. The new pattern requires
"native " + an Indigenous noun, so "native- born" / "native-born" / "native population" never match.

Before -> after (verified live):
- "women sterilized without their consent" (federal): BEFORE coerced-sterilization-indigenous +
  attribution notice + Hope for Wellness + MMIWG + 9-8-8 (the "native- born" over-fire); AFTER
  coerced-sterilization (generic) + 9-8-8 only, NO attribution notice, NO Indigenous-specific lines.
- Not regressed (verified live): "coerced sterilization of Indigenous women" -> full Tier A WITH the
  attribution notice + Hope for Wellness + MMIWG + 9-8-8; "residential school health conditions" ->
  full treatment WITH the attribution notice. Unit tests confirm "Native communities", "native people",
  and "native women" still upgrade, while "native-born", "native population", "native Canadians" do not.

## Fix B: the two lighter crisis topics require a cited basis

early-hiv-aids and tainted-blood-krever now fire their contextual note and 9-8-8 line only when the
topic appears in the question, in the answer text, or in a passage the kept answer actually CITES. A
match that comes only from a passage that was sent to the model (in_prompt) but never cited no longer
fires them. Residential-school and coerced-sterilization detection are unchanged (they still fire from
any answer-basis row). The existing hepatitis demotion is unchanged. The curated /stories and /flag
pins are the directly-shown record, so they are treated as a cited basis (their two topics still fire).

Before -> after (verified live):
- "informed consent requirements for surgery" (national): BEFORE Tier A note + 9-8-8 (early-hiv-aids
  from a CCDR HIV-testing-consent snippet that was retrieved but not cited; the answer is about surgical
  consent and has no HIV); AFTER NO care note.
- Preserved (verified live): "blood donor clinics in the 1970s" (national) still shows the note + 9-8-8
  (the answer says "HIV status"); "early HIV and AIDS response in the 1980s" still fires. Unit test
  confirms a CITED HIV passage still fires even when the answer text does not repeat HIV.

## The four verify queries, before -> after

| Query (scope) | Before | After |
|---|---|---|
| women sterilized without their consent (federal) | coerced-sterilization-indigenous: note + ATTRIBUTION + Hope for Wellness + MMIWG + 9-8-8 | coerced-sterilization (generic): note + 9-8-8 only, NO attribution, NO Indigenous lines |
| coerced sterilization of Indigenous women (federal, regression) | full Tier A + attribution + Hope/MMIWG/988 | unchanged -- full Tier A + attribution + Hope/MMIWG/988 |
| informed consent requirements for surgery (national) | Tier A note + 9-8-8 (incidental snippet HIV) | NO care note |
| blood donor clinics in the 1970s (national, preserved) | early-hiv-aids note + 9-8-8 | unchanged -- note + 9-8-8 (HIV in the answer) |

## Over-fire count

Answered non-care probes still showing a crisis line (committed open-input probe, pilot, cached):
- Was 6; now 4.
- Dropped by Fix B: p054 ("Ebola preparedness in 2014") and p171 ("tuberculosis ??") -- both were
  early-hiv-aids from an incidental in_prompt-only snippet.
- Still firing (4), each with a legitimate basis per Fix B: p002 and p137 (TB answers that discuss HIV),
  p034 (blood-safety answer about the blood system), and p138 (cites an HIV passage). These are the
  cited/answer basis the rule intends to keep.

## Verify (reports/open_input/pilot_keyed_v6.json)

- ERRORS 0; answered-with-unresolved-citation 0.
- No genuine covered-topic answer lost its note: every answered covered-topic probe that had its note
  before still has it (answered care_hit 34/37, unchanged; the 3 are the documented p091 coverage gap,
  p105 off-target, and p115 hepatitis -> Tier C).
- Abstentions still show nothing (Fix 1 from the prior pass, unchanged).
- Dosing still Tier C (p033 and the acetaminophen query).
- The heaviest two topics (residential-school, coerced sterilization) unchanged; no Indigenous-upgrade
  churn in the probe set (Fix A only affected the demographic-"native" verify case).
- Backend `pytest` 382 passed (incl. the new native-demographic and cited-basis tests); frontend
  `vitest` 73 passed; `tsc --noEmit` clean; `vite build` clean.
- Both scopes, both widths, zero console errors. Frozen set byte-identical.

## Files changed (for your commit; nothing run here)

This commit also carries the prior pass's abstention + dosing fixes (same working tree):

    src/archive_debugger/flags.py          # Fix A native-phrase; Fix B cited-basis; (+ prior dosing topic)
    src/archive_debugger/api/app.py        # Fix B /stories + /flag cited basis; (+ prior abstention None)
    tests/test_flags.py                    # Fix A + Fix B tests; row() default cited
    tests/test_api.py                      # (prior) abstention-shows-no-care test
    web/src/App.tsx                        # (prior) interstitial gated on !abstentionOnly
    web/src/lib/sensitivity.ts             # (prior) dosing-treatment-guidance in TIER_C
    web/src/test/care.test.tsx             # (prior) Tier C partition includes dosing

Commit message carries no attribution line, matching this public repo.
