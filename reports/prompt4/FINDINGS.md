# Prompt 4 - CARE-aligned vocabulary and care layer

Verification pass deliverable. All changes are the tool's own voice, labels, notices, and
care-detection config; the historical record is untouched. Nothing committed or deployed.
Screenshots and JSON logs are in this folder (reports/prompt4/). ASCII only.

## The one hard line: the record is unchanged (proven)

No scanned page, OCR string, stored passage, real title, or displayed excerpt was altered. The proof
is structural: every change is in web/src/ (frontend) or docs/. Nothing under src/archive_debugger/
(the layer that serves record data) was edited, so the record-bearing endpoints - /ask evidence,
/stories, /pages, /examples - are byte-identical by construction. The attribution notice and the
crosswalk are derived client-side from the topics the backend already returns; they add no backend
path. Backend tests still pass 356/356, confirming serve behavior is unchanged.

## Change 1 - vocabulary and governance claims

The tool's chrome was audited for its own voice. The record's own words (including "Indian" in
document titles and OCR) are never touched. The tool's vocabulary was already largely respectful; the
real issue was an overclaim of governance.

Changed (tool's own voice):

- About, "Care and consent": removed "We follow the CARE principles ... and the First Nations
  principles of OCAP." Now "aligned with the CARE Principles for Indigenous Data Governance ... and
  informed by the Local Contexts Notices and the First Nations principles of OCAP," followed by an
  explicit, plain statement: not community-governed, not certified, and not reviewed or endorsed by
  any community; real governance notices are made by the institution with the communities; what the
  tool adds is context alongside the record, never edited into it; rationale in docs/CARE.md. Reason:
  "follow OCAP" overclaims - OCAP governs First Nations' control of their OWN data; a third-party index
  of state records cannot "follow" it.
- Gaps "A note on care": same softening (from "guided by CARE and OCAP principles" to "informed by the
  CARE Principles and the Local Contexts Notices"), plus the attribution acknowledgement and the plain
  non-governance statement. Added a care note to the PILOT Gaps page, which had none, so both scopes
  carry the stance (the pilot holds residential-school and sterilization content too).
- "harm to Indigenous people" -> "harm to Indigenous communities" in the care notes.

Kept deliberately (and why):

- "National Indian Residential School Crisis Line" (crisis.py): the official name of the real,
  verified support line. Renaming it would misname a service.
- "Metis" without the accent (crisis.py): the codebase is ASCII-only by project rule; this is the
  standard ASCII rendering.
- The detector regexes in flags.py (e.g. "indian residential"): they match the record's own historical
  words so the care layer can find the content; never displayed, and changing them would reduce recall
  and regress the care layer.
- contextualNoteDefault (sensitivity.ts): deliberately group-agnostic, so it never names a specific
  community; correct for a note that can fire on broad eugenics-era content.
- All seed and probe question text (eval): not touched (frozen gold, N4; not the tool's voice).

FLAGGED for Jake's / IAC's decision:

- The exact wording of the governance statements (About, Gaps) and the attribution notice. These
  should be the project's and IAC's call, not mine. I wrote honest, non-overclaiming drafts.
- Whether to enable the crosswalk (below) and the exact term list.

## Change 2 - attribution-incomplete notice (shipped, ON)

A short notice, in the spirit of the Local Contexts Attribution Incomplete Notice, worded as the
tool's own acknowledgement (not an official Notice). It fires for exactly the two topics that are
records created about an Indigenous community by the state without its involvement:
residential-school-health and coerced-sterilization-indigenous (the same two that trigger the
interstitial). Copy is in sensitivity.ts (ATTRIBUTION_NOTICE); component is AttributionNotice.tsx.

Where it renders (every path the existing care note fires, plus the interstitial):

- In the contextual note (answer, compare, and limited-mode results), between the note and the crisis
  lines. Screenshot: care_elem_pilot_residential.png (note + "Attribution incomplete" + crisis lines).
- In the interstitial, before the crisis lines. Screenshot: care_elem_ml_sterilization.png.

Precision (no false positives): HIV/AIDS and tainted-blood results get the contextual note and crisis
lines but NOT the attribution notice. Screenshot: care_elem_ml_hiv.png (no attribution block). The
gating is unit-tested (needsAttribution true only for the two topics).

Crisis line intact and uncrowded: the attribution notice is its own block with a lighter rule; the
verified crisis lines render unchanged beneath it (see the screenshots). On a pure abstention the
contextual note is suppressed by the existing frozen design (nothing harmful foregrounded), so the
attribution notice is not shown on that result either - consistent with "every path the care note
fires"; the interstitial still carries it before the abstention is shown.

Verified live (both scopes, phone + laptop), zero app console errors: after_results.json.

## Change 3 - reparative term crosswalk (built, OFF behind a flag)

Built the full data path and left it OFF (CROSSWALK_ENABLED = false in sensitivity.ts), per the
brief's own fallback, because even "unambiguous" terms carry some false-annotation risk and the term
list should be IAC's and the communities' call.

- Data: COLONIAL_TERM_CROSSWALK, seeded with only clearly unambiguous pairs - Eskimo -> Inuit, and
  half-breed -> Metis. Deliberately EXCLUDED: "Indian" (a legal status under the Indian Act and part of
  place and institution names - no single correct replacement) and "Aboriginal" (still used in some
  official contexts; not a clear error).
- Rendering: CrosswalkText.tsx annotates matched terms in a displayed excerpt WITHOUT rewriting them -
  the record's word stays; the contemporary term is shown beside it as the tool's annotation. Wired
  into the compare excerpt (CompareView).
- OFF behavior proven: with the flag off, the compare excerpt renders with no annotation
  (compare_crosswalk_off.png; no "today:" marker anywhere), and no benign content is touched.
- ON behavior unit-tested (care.test.tsx): only "Eskimo"/"half-breed" are marked; "Indian Act",
  "Indian Affairs", and benign words are left alone; the original text is preserved exactly.
- To enable after review: set CROSSWALK_ENABLED = true, confirm the term list with IAC and the
  communities, and extend the wiring from the compare excerpt to the evidence trail (noted in
  docs/CARE.md). I did not produce a live screenshot of it ON because that needs a compare excerpt
  containing one of the terms; say the word and I will enable it and capture one.

## Change 4 - rationale doc

docs/CARE.md: the governance stance (what the tool is and is not), CARE Principles alignment, Local
Contexts Notices the tool is ready for, the full vocabulary term-decision list, the attribution
notice, and the crosswalk (off, seed list, how to enable). This is what Jake shows IAC.

## Non-negotiables honored

- Retrieval, generation, the frozen abstention rule, and the eval: untouched. No backend change at
  all. The honesty gates behave exactly as before (backend tests 356/356).
- The existing care layer: strengthened, not replaced. The contextual note, verified crisis lines, and
  the interstitial all still fire; detection stays precision-first and evidence-based (no new false
  positives - the attribution notice reuses existing topics, the crosswalk is off).
- No overclaim of governance: the copy now says CARE-aligned and Notices-ready, not community-governed
  or certified, and states plainly that no community has reviewed or endorsed the tool.
- One network call at runtime, no new dependency, degrade-never-error: unchanged (all additions are
  static client copy/config).

## Tests and build

- Build: passes (vite build, 90 modules).
- Frontend: 70/70 (vitest) - the 65 existing plus 5 new care tests.
- Backend: 356 passed (pytest), unchanged.
- Typecheck: clean (tsc --noEmit).

## Screenshots (reports/prompt4/)

- care_elem_pilot_residential.png - contextual note + attribution notice + crisis lines (pilot).
- care_elem_ml_sterilization.png - interstitial + attribution notice + crisis lines (microlog).
- care_elem_ml_hiv.png - contextual note + 988 only, NO attribution notice (precision).
- attr_*_{laptop,phone}_{interstitial,result}.png - full-page, both scopes, both widths.
- about_after_{laptop,phone}.png - the reworded governance copy.
- gaps_{pilot,microlog}_after_{laptop,phone}.png - the care notes (pilot now has one).
- compare_crosswalk_off.png - compare excerpt with the crosswalk off (no annotation).
- Before state: reports/prompt3/ (nav_about.png, nav_gaps.png, care_*.png) is the genuine pre-change
  state; the attribution notice and the governance rewording are the difference.

## Files changed

Frontend: web/src/lib/sensitivity.ts; web/src/components/AttributionNotice.tsx (new);
web/src/components/CrosswalkText.tsx (new); web/src/components/ContextualNote.tsx;
web/src/components/Interstitial.tsx; web/src/components/CompareView.tsx;
web/src/components/pages/About.tsx; web/src/components/pages/Gaps.tsx;
web/src/test/care.test.tsx (new). Docs: docs/CARE.md (new). No src/archive_debugger/ change.

## For your / IAC's decision

1. Approve or edit the governance wording (About, Gaps) and the attribution notice text.
2. Decide whether to enable the crosswalk, and confirm its term list, with the communities where
   possible. It is off until you say so.
3. Confirm the crisis lines are current the week of the event (crisis.py docstring already says to
   re-verify; unchanged here).
