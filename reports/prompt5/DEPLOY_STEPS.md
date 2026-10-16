# Festival finalize - the steps for you to run (I did not run any of these)

Nothing here was executed. These are the exact Railway environment change and the git commit and
deploy steps for you to run yourself.

## 1. Railway environment change

Only one behavioral change is needed for the festival:

- REMOVE the `CIVIC_DEFAULT_SCOPE` variable (it was `microlog`). With it unset, the live site lands
  on the federal pilot (the Alberta disagreement), the label and the data agree, and the scope
  switcher reaches the national (microlog) scope and its own stories. This is the pilot-default
  behavior verified in Task 3. (Leaving it set to `microlog` reintroduces the prompt-3 landing
  mismatch; removing it is the fix.)

Confirm these stay as they are:

- `ANTHROPIC_API_KEY` = your valid key. On Railway this is read directly from the service variables,
  so the local .env / session-variable shadowing that caused the 401s here does not apply. The key
  you set works as a standard x-api-key.
- `CIVIC_ENABLED_SCOPES=pilot,microlog` (both corpora served), the R2_* variables, and `PORT` -
  unchanged.

Railway redeploys automatically when a variable changes; if not, trigger a redeploy.

## 2. Git commit (source only; the image rebuilds the web)

web/dist is gitignored and the Dockerfile builds the web inside the image (node stage, npm ci, npm run
build), so do NOT commit web/dist - the deploy rebuilds it from source. .env is gitignored, so the key
is never committed. The reports/ screenshot folders (reports/prompt4, reports/prompt5,
reports/deck_shots, reports/open_input) are local deliverables; they are not needed on the server, so
leave them out of the commit (or add them to .gitignore).

The source files to commit (the CARE vocabulary/care-layer work plus the earlier staged audit fixes):

    # from the repo root
    git add \
      web/src/lib/sensitivity.ts \
      web/src/components/AttributionNotice.tsx \
      web/src/components/CrosswalkText.tsx \
      web/src/components/ContextualNote.tsx \
      web/src/components/Interstitial.tsx \
      web/src/components/CompareView.tsx \
      web/src/components/pages/About.tsx \
      web/src/components/pages/Gaps.tsx \
      web/src/App.tsx \
      web/src/hooks/useExamples.ts \
      web/src/test/care.test.tsx \
      src/archive_debugger/flags.py \
      scripts/open_input_probe.py \
      scripts/open_input_probes.jsonl \
      docs/CARE.md

    git status          # confirm only the intended files are staged
    git diff --cached   # review

Commit (you are on `main`; create a branch first if you prefer):

    git commit -m "CARE-aligned vocabulary and care layer; thin-chip and care-detection fixes

    - Attribution-incomplete notice on residential-school and sterilization results (frontend-only)
    - Governance wording aligned with CARE, Notices-ready, non-overclaiming (About, Gaps)
    - Reparative term crosswalk built but OFF behind a flag
    - Thin-record example chip prefers a verified refuse probe (q039), not q015
    - Care detection adds British sterilis* spelling, precision preserved
    - No change to retrieval, generation, the abstention rule, the eval, or any audited number

    Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

    git push            # push the branch you committed on

## 3. Deploy

- Make the Railway variable change (step 1) and push the commit (step 2). Railway rebuilds the image
  (which runs npm run build, so the new web ships) and redeploys.
- The pilot files are provisioned from R2 / the GitHub release as before; no data change.

## 4. Post-deploy sanity (on the live URL)

- The bare URL lands on the federal pilot with the Alberta 1974 vs 1999 disagreement; the "About this
  corpus" strip reads the pilot numbers.
- The scope switcher's "National public health, all provinces" loads the microlog corpus and its own
  stories (the CCDR notifiable-disease compare).
- Ask a COVID-2020 question (the "see it decline" doorway) and confirm it declines.
- Open a residential-school or sterilization result and confirm the contextual note, the attribution
  notice, and the crisis lines render together. (Do not feature this; it is for a spot check.)
- Confirm answers generate (the key is valid), so you are not seeing limited mode.
