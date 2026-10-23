# Deploy steps (you run these; nothing here was executed)

Covers the full pre-festival care pass: the three tiers + cold-start warm + Explore scroll, and this
precision follow-up (coerced tubal ligation / without-consent in Tier A, Indigenous-context gating of
the attribution notice and Indigenous lines, accent-insensitive French). All additive and freeze-safe.

## 1. No Railway environment change

Nothing in this work needs an environment change. Confirm the existing variables are unchanged:
- `CIVIC_DENSE_BACKEND=numpy` (keeps the dense index resident; the cold-start warm logs
  `dense=numpy-resident` per scope, or a plain `sqlite-vec scan (FALLBACK...)` line if an instance is
  too small to hold it - watch the boot logs after deploy).
- `CIVIC_ENABLED_SCOPES=pilot,microlog`, `ANTHROPIC_API_KEY`, the `R2_*` variables, `PORT` - unchanged.
- `CIVIC_DEFAULT_SCOPE` stays unset (pilot default landing).

## 2. Git commit (source only; the image rebuilds the web)

web/dist is gitignored and the Dockerfile builds the web inside the image, so do NOT commit web/dist.
The reports/ folder is a local deliverable; leave it out. The source files to commit:

    # from the repo root
    git add \
      src/archive_debugger/flags.py \
      src/archive_debugger/crisis.py \
      src/archive_debugger/api/app.py \
      web/src/lib/sensitivity.ts \
      web/src/components/LimitedModeCard.tsx \
      web/src/App.tsx \
      scripts/open_input_probe.py \
      tests/test_flags.py \
      web/src/test/care.test.tsx \
      docs/CARE.md

    git status          # confirm only the intended files are staged
    git diff --cached   # review

Commit (you are on `main`; create a branch first if you prefer). The message carries NO attribution
line, matching this public repo:

    git commit -m "care: three proportionate tiers, cold-start warm, Explore entry

    - Care layer split into three tiers: Tier A crisis care (residential-school, coerced
      sterilization, tainted-blood, early-HIV/AIDS), Tier B a calm historical-content note with no
      crisis line (human/reproductive sterilization, child-sexual content), Tier C a not-current-
      medical-advice note with no crisis line (immunization/vaccination schedules and doses, hepatitis
      transmission). Tier B/C map to no crisis resource.
    - Coerced tubal ligation and sterilization without consent are Tier A; plain voluntary tubal
      ligation stays Tier B.
    - The attribution-incomplete notice and the Indigenous-specific lines (Hope for Wellness, MMIWG)
      are shown only when the record shows Indigenous context, so a non-Indigenous Sexual Sterilization
      Act result no longer claims to be about an Indigenous community. Residential-school keeps the full
      treatment always.
    - A routine hepatitis-transmission answer no longer shows a suicide crisis line (demoted from an
      incidental HIV/blood title match to the Tier C note).
    - Care patterns match accent-insensitively, so accented French matches the ASCII patterns; the
      displayed record is never altered.
    - Bilingual care terms added (pensionnats, VIH, SIDA, sang contamine, sterilisation forcee, and so
      on), precision preserved.
    - Cold-start: the boot warm now runs a real retrieval per scope and primes the model client, logs
      the resident dense backend, and the limited-mode copy reads as still getting ready; no change to
      what /ask returns.
    - Explore: 'Explore this corpus' enters the corpus instead of reloading the Explore page to the top.
    - docs/CARE.md updated to match the shipped care layer: the three tiers, the Indigenous-context
      gating of the attribution notice and the Indigenous-specific lines, the detection surfaces and
      accent-insensitive French matching, and the crosswalk staying off.
    - No change to retrieval, generation, the abstention gate, the eval, or any audited number; the
      record and its endpoints are byte-identical."

    git push

## 3. Deploy

- Push the commit. Railway rebuilds the image (runs npm run build, so the new web ships) and
  redeploys. The pilot and microlog data are provisioned from R2 as before; no data change.

## 4. Post-deploy sanity (on the live URL)

- Bare URL lands on the federal pilot (Alberta disagreement); the scope switcher reaches the national
  (microlog) corpus.
- Ask "contaminated blood and hepatitis C": a "not current medical advice" note, NO suicide line.
- Ask "forced sterilisation" on the national scope: a contextual note and 9-8-8, and NO
  "about an Indigenous community" attribution notice (its answer is the BC Sexual Sterilization Act).
- Ask "coerced sterilization of Indigenous women": the attribution notice and the Indigenous lines
  (Hope for Wellness, MMIWG) appear. Open a residential-school result: the full treatment is unchanged.
- Confirm answers generate (not limited mode), and that the first question after an idle period answers
  within budget; check the boot logs show `dense=numpy-resident` for both scopes.
