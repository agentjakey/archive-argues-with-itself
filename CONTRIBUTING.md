# Contributing

Thank you for looking. This is a small, carefully measured tool; contributions
that keep it that way are the most useful.

## Issues

Two templates: a bug report and a corpus-gap report. A corpus gap is a question
the archive should be able to answer and the tool does not, a citation that opens
the wrong page, a date the metadata gets wrong, or an abstention that seems
wrong. Include the exact question text and filters (the URL carries them) and,
for citations, the passage id shown on the evidence card.

## Pull requests

- Run the suite first: `python -m pytest` and, in `web/`, `npm run typecheck && npm test && npm run build`.
- Keep the four rules (README, "The four rules"). Changes that add a network
  call outside `harvest/`, report text overlap as citation correctness, store
  page coordinates, or edit evaluation gold to improve a number will not be
  merged.
- Retrieval or generation changes must come with an evaluation run recorded in
  `eval_runs` and a report under `reports/`; numbers go in the report, not the
  commit message.
- Code is ASCII-only (no smart quotes, dashes or emoji), plain and explicit.
- Fill in the pull request template.

## Adding a scope

A second topic or jurisdiction is configuration, not code: a new
`config/pilot.toml` (topic term-set, collection clause, binning window, floor)
and a new `data/manifest/` produced by the harvest layer. Run the sizing audit
first (`archive_debugger.harvest.discover` and, for a jurisdiction,
`archive_debugger.harvest.bc_audit` as a template) and check the result against
the 2,500-item floor before harvesting anything;
`reports/bc_audit/bc_sizing.md` shows what a scope that does not clear the floor
looks like.

## Labels and judgments

Evaluation gold and support judgments are decided by a human and recorded with
their reasons under `eval/`. Do not change existing labels; extensions are
additive and go in a new file with a changelog line in `eval/labeling_notes.md`.

## Contributing and conduct

Issues are welcome, whether a bug, a corpus gap, or a second-scope idea; a small
example (the question URL, or a passage id) helps more than a long description.
Please be respectful and constructive, and open an issue for anything unclear
rather than guessing. Maintainer: Jacob Ortiz, https://github.com/agentjakey.
