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

One deliberate, approved exception has since been taken against this set: the dense
retrieval leg in `src/archive_debugger/retrieve/search.py` was changed for A4 (in-memory
dense retrieval) and the pilot eval was re-frozen on the new backend. See "## A4:
in-memory dense retrieval (approved re-freeze)" below. Everything else in the frozen set
is still byte-identical to the baseline.

## A4: in-memory dense retrieval (approved re-freeze)

A4 replaces the dense leg's per-row sqlite-vec scan with an exact, resident in-memory cosine
(`CIVIC_DENSE_BACKEND=numpy`), because on the deployed instance an uncached microlog query
spent about 23 seconds in the per-row scan (warming gave no gain; the index was not resident).
The in-memory leg returns the identical dense candidate set (top-200, 200/200 on the pilot and
microlog indexes) in tens of milliseconds. It is exact; the only movement is tie order at
near-identical distances. This exception was explicitly approved, with a full re-eval and this
re-freeze.

Files changed for A4 (search.py is the one frozen-set file touched, by approval):
- `src/archive_debugger/retrieve/dense.py` (new): the resident DenseIndex + exact cosine, a
  memory-fit guard (reads the cgroup limit; falls back to sqlite-vec rather than OOM), and the
  `CIVIC_DENSE_BACKEND` switch (default `sqlite`).
- `src/archive_debugger/retrieve/search.py` (frozen, approved exception): `_dense` uses the
  resident index when present; the sqlite-vec scan remains the default and the fallback.
- `src/archive_debugger/api/app.py`: one resident index per scope, shared across the pool.
- `pyproject.toml`: `numpy` pinned as a direct dependency.
- `tests/test_retrieve.py`: a numpy-vs-sqlite parity test on the fixture.
- `src/archive_debugger/eval/report.py`: records the dense backend in the eval report.

Re-eval diff (pilot, the audited scope), sqlite -> numpy:
- recall@5 / @10 / @20: unchanged (0.2438 / 0.4581 / 0.7276).
- abstention leakage and unjudged@10/@20: unchanged.
- nDCG@10: 0.5082 -> 0.5084, from one tie reorder on q021 (same retrieved set, order-sensitive
  metric nudged). This is the single moved number.
- microlog: recall over all 40 decided-gold seeds is unchanged (recall@5/10/20 identical; pooled
  gold is insensitive); one of the 40 (mq39) has a top-10 set that differs by one passage, because
  microlog has more near-tie distances. Diff run over the committed microlog gold
  (`reports/microlog/gold_decisions.json`) with question text from the judgment worksheet; no
  committed microlog eval-report harness exists (its civic.db carries no eval schema), so the
  judgment-derived numbers (support, abstention) are the manual N2 audit and are backend-
  independent (computed over the cached answers).

Re-freeze performed here:
- `reports/phase7/eval_report.json` and `.md` regenerated on `CIVIC_DENSE_BACKEND=numpy`; both
  now record `dense backend: numpy`. nDCG@10 reads 0.5084.
- Repository and test default stay on `sqlite`; the parity test guards equivalence; numpy is the
  deploy variable only.

Still carrying the pre-A4 (sqlite) retrieval numbers, to reconcile on numpy at the same commit
(flagged, not silently changed): `docs/evaluation/retrieval_report.md` and
`reports/phase16/audit_numbers.json` (`recall_final_gold.ndcg@10` = `[0.4174, 0.5082]`, parsed
from that md). Regenerating the retrieval sweep on numpy is the clean way to update both; it is
a separate step because it re-runs the full sweep and may surface further tie-order nudges. The
headline recall values in those files are unchanged by A4; only nDCG@10 moves by +0.0002.

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
| src/archive_debugger/retrieve/search.py | bccbf78 (2026-09-11), then CHANGED by A4 (dense leg; approved re-freeze above) |
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
