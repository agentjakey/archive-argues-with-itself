# Freeze checklist

The ship gate for the festival build. It records what is frozen, proves the frozen set
was not touched by the hardening work, separates the checks that can be confirmed now
from the ones that are the operator's, and lists the release commands.

## What is frozen (N5)

Frozen until after the festival: the abstention gate and the salient-term rule
(`src/archive_debugger/stopwords.py`), the retrieval configuration
(`src/archive_debugger/retrieve/search.py`, `src/archive_debugger/retrieve/config.py`),
the generation logic (`src/archive_debugger/generate/llm.py`,
`src/archive_debugger/generate/answer.py`), and every audited number
(`reports/phase16/audit_numbers.json`). No change in the hardening phases may move a
published metric or alter these files.

## Freeze baseline

Baseline commit `ba29a88` ("update gate due to prompt phrase diffs"), the last commit
before the offline-hardening work began. This is the audited and publicly released
system, with the frozen files at their locked content. Everything below is the change
since that baseline.

## Frozen set was not touched (confirm now)

```
git diff --stat ba29a88 -- src/archive_debugger/stopwords.py \
  src/archive_debugger/retrieve/search.py src/archive_debugger/retrieve/config.py \
  src/archive_debugger/generate/llm.py src/archive_debugger/generate/answer.py \
  reports/phase16/audit_numbers.json
```

Empty output means untouched. Each frozen file was last modified before the baseline and
has not changed since:

| frozen file | last modified |
| --- | --- |
| src/archive_debugger/stopwords.py | d7d02a9 (2026-09-11) |
| src/archive_debugger/retrieve/search.py | bccbf78 (2026-09-11) |
| src/archive_debugger/retrieve/config.py | bccbf78 (2026-09-11) |
| src/archive_debugger/generate/llm.py | ad32aa8 (2026-09-10) |
| src/archive_debugger/generate/answer.py | ee81f3c (2026-09-11) |
| reports/phase16/audit_numbers.json | 57320d0 (2026-09-11) |

The doc-hygiene edits that touched files carrying numbers (README.md, docs/METHODS.md,
docs/gaps.md) changed wording and one rounding only; a numeric diff against the source
confirms no audited value moved, and the honesty disclosure paragraph is byte-identical
wherever it appears.

## Changed files since the baseline

Reproduce with `git diff --name-only ba29a88` (committed and working tree) plus the new
untracked files from the freeze pass. None of the six frozen artifacts above is among
them.

Backend and API:
- src/archive_debugger/api/app.py (offline degradation, `flagged`, `ocr_quality`, `/stories`, `/flag`)
- src/archive_debugger/flags.py (new: harm-adjacent detection over served evidence)

Eval and report generators (date-header stamp only; no number changed):
- scripts/audit_report.py
- src/archive_debugger/eval/report.py
- src/archive_debugger/eval/retrieval_sweep.py

Offline scripts and the ship gate:
- scripts/preflight.py (new)
- scripts/scan_coverage.py (new)
- scripts/offline_walkthrough.py (new)
- scripts/demo_selftest.py (new, this pass)

Tests:
- tests/test_api.py
- tests/test_flags.py (new)

Frontend:
- web/index.html (share and preview tags)
- web/src/main.tsx, web/src/App.tsx, web/src/types.ts
- web/src/hooks/useAsk.ts
- web/src/lib/api.ts, attract.ts, sensitivity.ts, urlstate.ts
- web/src/components/AskBar.tsx, AttractHero.tsx, CompareView.tsx, ContextualNote.tsx,
  CrisisLines.tsx, EntryAdvisory.tsx, ErrorBoundary.tsx, EvidenceCard.tsx, Interstitial.tsx,
  KioskQr.tsx, LimitedModeCard.tsx, OcrBadge.tsx, PageDrawer.tsx, QuestionTiles.tsx

Docs:
- README.md, docs/METHODS.md, docs/gaps.md, docs/writeup.md
- docs/RUNBOOK.md (rewritten, this pass)
- docs/FREEZE.md (new, this pass)

## Gates that can be confirmed now (automated)

- `pytest` (backend suite, including tests/test_flags.py and tests/test_api.py).
- `vitest` (web unit tests, if configured under web/).
- `scripts/offline_walkthrough.py`: green, all checks, cache intact.
- `scripts/preflight.py`: green on every check except the page pack on an unbuilt box.
- Doc-hygiene numeric diff: clean, no audited value moved, disclosure byte-identical.

## Gates that are the operator's (manual)

- The page-pack build (network on) and a green offline self-test on the festival laptop.
- The screenshot passes for the compare view, the sensitivity layer (entry advisory,
  contextual note, crisis lines, interstitial, OCR badge), the attract screen, the flagged
  story permalink, and the user-pinned flagged compare.
- The phone QR scan against the live URL.
- The sensitive-query pre-test: re-verify the crisis numbers the week of the event and
  complete any Indigenous-health featuring consult.
- OS kiosk lockdown: auto power-on, auto-login, boot task for the API and the kiosk
  browser, and the watchdog that relaunches them.

## Final ship condition

A GREEN `scripts/demo_selftest.py` on the festival laptop, with the Wi-Fi off. On a fresh
box it is RED only on the unbuilt page pack; build the pack (docs/RUNBOOK.md, section 3)
and it goes green.

## Release commands (run these yourself; not run here)

```
git add -A
git commit -m "chore(freeze): festival build - demo self-test, runbook, freeze checklist; gaps wording"
git tag -a v1.0-festival -m "Festival build (Futureproof, Vancouver, 2026-10-28): offline civic-memory debugger over Democracy's Library. Frozen per N5."
git push origin main
git push origin v1.0-festival
```
