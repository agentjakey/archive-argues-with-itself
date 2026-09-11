**What this changes**

**Why**

**Checks**

- [ ] `python -m pytest` passes
- [ ] in `web/`: `npm run typecheck && npm test && npm run build` pass
- [ ] no network call added outside `harvest/`
- [ ] citation verification still the three structural checks; no overlap score reported as correctness
- [ ] no coordinate storage; page-level deep links unchanged
- [ ] no evaluation gold edited; any extension is additive, in a new file, with a changelog line in `eval/labeling_notes.md`
- [ ] retrieval or generation change: evaluation run recorded in `eval_runs` and a report under `reports/`
- [ ] ASCII-only code; README and docs updated where behaviour changed
