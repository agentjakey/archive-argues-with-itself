# Prompt 3 verification - closing the two (three) gaps

Verification pass on the branch with the Task 5 staged fixes. Real app, real clicks, real
screenshots. Nothing committed, nothing deployed. Screenshots and JSON logs are in this folder
(reports/prompt3/). ASCII only.

## Headline

- The pilot DOES boot locally. The earlier "cannot boot, vectors.db absent" was a wrong path
  check: the pilot data was at the deploy location C:\civic-data (civic.db 1.79 GB, index
  vectors.db 1.49 GB) the whole time, which .env points CIVIC_DB_PATH / CIVIC_INDEX_PATH at. Both
  scopes loaded resident (numpy): pilot 745,893 vectors, microlog 1,136,827 vectors.
- Gap 1 (demo path) and Gap 3 (click-through) are verified. Zero app-origin console errors across
  everything driven. The thin-chip fix is confirmed live on pilot. The refusal is an honest, calm
  decline. The care layer (interstitial + contextual note + crisis lines) renders on both scopes.
- Gap 2 (keyed free-text honesty) is BLOCKED: the ANTHROPIC_API_KEY in .env is rejected by the API
  (HTTP 401 invalid x-api-key). Generation cannot run until a valid key is provided. The harness is
  ready; the run is one command once the key works.
- One significant pre-existing finding surfaced (national-landing scope mismatch). Flagged, not
  fixed, because it touches the scope-routing contract and the byte-identical pilot path.
- Build passes. Frontend tests 65/65. Backend tests 356 passed.

## How it was driven

- Playwright (already in the venv, version 1.63.0 - not a new dependency) driving the system Edge
  via channel="msedge", headless. Real clicks, console and pageerror captured per step.
- Server: one multi-scope process (CIVIC_SERVE_SCOPES=pilot,microlog, CIVIC_DENSE_BACKEND=numpy,
  CIVIC_DEFAULT_SCOPE=microlog) serving the built web/dist same-origin, reproducing the festival
  deploy. Stopped after the run.
- "App console error" counts exclude third-party warnings emitted by archive.org's own embed iframe
  (a benign custom-element double-registration, "ia-activity-indicator"); those are not our code.

## Gap 1 - pilot boot and the demo path (VERIFIED, with one caveat)

Screenshots 01..08 plus landings. gap1_results.json has the raw per-step log (all steps:
console_errors = 0).

- National landing (01_national_landing_bare.png): renders. SEE FINDING 1 - under
  CIVIC_DEFAULT_SCOPE=microlog the bare URL shows microlog's label/facts but the pilot's stories.
- microlog real content reachable via ?scope=microlog (01b_microlog_explicit.png): its own featured
  story is the CCDR notifiable-disease compare, confirming microlog's authored stories exist and
  render.
- Federal pilot landing (02_pilot_landing.png): featured story = the Alberta 1974-vs-1999 health
  insurance compare (ThresholdHero), consistent label and facts (3,477 items, 745,893 passages,
  1960 to 2009).
- Alberta compare (03_alberta_compare.png): opens from the threshold, compare title "1974 vs 1999",
  both scanned pages render (1974 Alberta Health Care Insurance Commission; 1999 Blue Cross
  statistical supplement). Signature moment intact. Both story pins resolve on the pilot civic.db.
- View the scanned page (04_page_drawer.png): the in-app PageDrawer opens with the page image and
  the archive.org deep link (https://archive.org/details/ableg_33398004781505/page/n52), a valid
  page-level IA link.
- Refusal, "See it decline" (06_refusal.png): q039 (COVID-19 in 2020) returns the honest, calm
  decline: "No answer from the record / the record here is thin: no retrieved passage mentions
  covid, 2020 (0 of 12 retrieved passages are undated)". No crisis line, no contextual note on the
  pure-abstention path (correct suppression). This path is CODE-decided (the frozen thinness gate),
  so it works even with the model unreachable.
- Thin-record chip (07_thin_chip.png, also visible in offline_degrade.png): the only chip tagged
  "(thin record)" is q039 (COVID-19 2020), NOT q015 (reproductive technologies). The Task 5 thin-chip
  fix is confirmed live on the pilot.
- Care layer on pilot (08_care_pilot.png): asking the HIV seed question renders the contextual note
  "A note on this record ... This is a government document from 1990 ..." with the 9-8-8 support line.

Caveat (see FINDING 2): because the API key is invalid, the Alberta compare and the HIV question
show the designed limited-mode card ("Showing the record, not a written answer") instead of a live
generated, cited answer. The retrieval, the pages, the compare, the care note, and the abstention
all render correctly; only the model-written paragraph is missing, and only because of the key.

Minor (FINDING 3): clicking the site title while a result is on screen does not return to the clean
landing (the result persists). A kiosk "home" reset (full reload) does clear it.

## Gap 2 - keyed free-text honesty (BLOCKED on an invalid key)

The committed 188-probe set (scripts/open_input_probe.py + scripts/open_input_probes.jsonl) is ready
to run keyed. It cannot be run until a valid key is in place, because the ANTHROPIC_API_KEY in .env
returns HTTP 401 (invalid x-api-key). Confirmed three ways: the server logged
outcome=degraded:model_unreachable for every answerable ask, and a direct SDK call via the app's
exact path (messages.parse with output_format + extra_body temperature, anthropic==1.5.0) returned
401 on three attempts. The key is well-formed (sk-ant-api03..., length 108, no quoting/whitespace),
so it is revoked/expired, not malformed. The same key is in both .env and the session environment.

What is already known without the key:
- Degrade-never-error holds: every answerable ask returned a 200 limited-mode card, never a crash or
  raw error (confirmed again in the browser; see Gap 3 offline-degrade).
- The code-decided abstention (frozen thinness gate) fires pre-model: q039 abstained correctly with
  no model call.

Frozen baseline for the comparison the brief asks for (reports/phase16/audit_numbers.json):
- off_target_answers = 5 on the 50-question seed audit (should-abstain questions answered with
  cited, supported sentences addressing a different question).
- holdout gold_abstain = 9/10 (one held-out gold-abstain question, h009, was answered); one
  gold-answerable (h015) abstained.

Run command once a valid key is set (pilot scope, isolated scratch cache so the demo cache stays
clean, paced to stay under the process rate limiter at 0.5 req/s):

    # 1. valid ANTHROPIC_API_KEY in .env
    # 2. boot pilot-only, numpy, scratch cache:
    CIVIC_DENSE_BACKEND=numpy CIVIC_CACHE_PATH=reports/open_input/probe_cache.db \
      .venv/Scripts/python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
    # 3. one pass, paced:
    .venv/Scripts/python.exe scripts/open_input_probe.py --base http://127.0.0.1:8000 \
      --scope pilot --pace 2.0 --out reports/open_input/pilot_keyed.json

Expected call count: about 185 model calls (188 probes minus the 3 empty/whitespace probes that
short-circuit pre-model), one pass, no retries. I will not run this on your key without your go.

## Gap 3 - click-through, both scopes, both widths, kiosk and offline (VERIFIED)

gap3_results.json has the full matrix. Nine combinations driven: pilot and microlog, laptop
(1440x900) and phone (390x844), plus kiosk and offline at laptop, plus the bare default. Every nav
link, the scope switch, the threshold story, the compare, the page drawer (open and close), kiosk
affordances, and offline affordances were clicked for real.

- App-origin console errors across all nine combos: 0.
- Every nav click landed on the right page (verified by document title). Scope switch reloads into
  the chosen corpus. Drawer opens and closes. No dead click, no wrong destination.
- Kiosk (combo_pilot_laptop_kiosk.png, combo_microlog_laptop_kiosk.png): QR present ("Take it with
  you"), filter selects hidden, enlarged type. The attract loop was pinned off with idle=36000 for
  the screenshots.
- Offline (combo_pilot_laptop_offline.png, combo_microlog_laptop_offline.png): the ask box is hidden,
  stories and the "See it decline" doorway remain, nav works.
- Phone (combo_pilot_phone_normal.png, combo_microlog_phone_normal.png): layout holds at 390 px.
- True-offline degrade (offline_degrade.png): with /ask aborted at the network layer, submitting a
  question shows "Can't reach the archive server. If you are at the exhibit, the record is still
  here; try an example question or a story below." No raw error leaked to the UI. (The one browser
  console "error" is the deliberate net::ERR_FAILED from the aborted request, not an app error.)

## Care layer (VERIFIED on both scopes) - the safety-critical check

care_results.json plus care_*.png. Flags are computed on serve from the evidence, so they render
even in limited mode; this verification is key-independent.

- Interstitial (the two heaviest topics) gates the result on BOTH scopes:
  - microlog residential schools -> interstitial (care_ml_residential_interstitial.png)
  - microlog sterilization -> topics ["coerced-sterilization-indigenous"], interstitial
    (care_ml_sterilization_interstitial.png)
  - pilot residential schools -> topics ["residential-school-health"], interstitial
    (care_pilot_residential_interstitial.png): "Before you continue / This result includes
    difficult historical content".
- Contextual note + crisis lines for the lighter care topics:
  - microlog HIV/AIDS -> topics ["early-hiv-aids"], contextual note (care_ml_hiv.png)
  - microlog tainted blood -> topics ["early-hiv-aids","tainted-blood-krever"], contextual note
    (care_ml_tainted.png)

No harm-adjacent result was surfaced without its care treatment in any case driven. The only path
that suppresses the note is a pure abstention (the record is silent), which is by design and does
not surface harm content.

## Findings to flag

FINDING 1 (HIGH, pre-existing, NOT caused by the staged fixes) - national-landing scope mismatch.
  With CIVIC_DEFAULT_SCOPE=microlog (the value docs/deploy.md specifies), the bare landing URL
  displays microlog's label and corpus facts but serves the pilot's stories, examples, and asks,
  because no-scope requests route to the base scope (pilot) while the display keys off the landing
  scope (microlog). Worse, the switcher can never route to microlog data: selecting "National"
  drops ?scope back to the bare URL (base = pilot), so microlog's authored stories/examples are
  unreachable through the UI. Evidence: /stories (no scope) and /stories?scope=pilot are identical
  (the 4 pilot stories); /stories?scope=microlog returns the 4 microlog stories; 01_national_landing
  _bare.png shows the microlog label over the pilot Alberta story.
  - Zero-code workaround (verified consistent): run with the pilot as the default landing
    (CIVIC_DEFAULT_SCOPE unset or = pilot). Then the bare URL is pilot (label and data agree) and
    the switcher reaches microlog via ?scope=microlog consistently. The demo then reads as
    "Federal pilot landing (the Alberta signature) -> switch to National (microlog breadth)".
  - If you want microlog to be the FIRST screen, the frontend needs a small routing change (make
    the default landing scope drive the data requests, and have the switcher always emit ?scope).
    I did not make it: it changes the no-scope routing and the byte-identical pilot request path,
    which is a deliberate design contract. Your call.

FINDING 2 (BLOCKER for Gap 2, environment) - the ANTHROPIC_API_KEY is invalid (HTTP 401). Every
  generated answer degrades to limited mode. The festival deploy needs a valid key for live answers.
  Provide a valid key (update .env) and I will run the single keyed 188-probe pass and report the
  honesty counts and the off-target comparison.

FINDING 3 (LOW, UX) - clicking the site title with a result on screen keeps the result rather than
  returning to the clean landing. Not a routing error; a kiosk reset clears it. Flagged only.

FINDING 4 (INFO, third-party) - archive.org's embed iframe logs a benign console warning
  (ia-activity-indicator custom-element double registration) when the page drawer opens online. Not
  our code, not an error; listed so it is not mistaken for an app fault.

## What could not be verified, and why

- Live generated, cited answers in the UI, and the Gap 2 keyed honesty counts: blocked by the
  invalid key (FINDING 2).
- A live-deploy check: the deploy is scaled to zero; everything here was verified locally against
  the same data and the built app.

## Changes made in this pass

- None to the app, config, or eval. This was verification only. The only staged changes remain the
  Task 5 fixes (web/src/hooks/useExamples.ts, web/src/App.tsx, src/archive_debugger/flags.py), which
  this pass confirms live. New untracked artifacts: reports/prompt3/ (this report, screenshots,
  JSON logs).

## Tests

- Web build: passes (vite build, 88 modules).
- Frontend: 65/65 (vitest).
- Backend: 356 passed, 1 benign deprecation warning (pytest).

## Manual - what you decide or do next

1. Decide on FINDING 1 (national-landing): run pilot-default (zero code) or ask me to prepare the
   frontend routing fix (flagged, not made).
2. Provide a valid ANTHROPIC_API_KEY so I can run the one keyed Gap 2 pass.
3. Review the screenshots in reports/prompt3/. Nothing is committed or deployed.
