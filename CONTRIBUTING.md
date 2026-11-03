# Contributing

Thank you for looking. Small, careful changes are the most useful.

## Good first issues

Issues labelled [good first issue](https://github.com/agentjakey/archive-argues-with-itself/labels/good%20first%20issue)
are small and self-contained. Each one names the files to change and how to check the result.

## Reporting a problem

Use the issue templates. A corpus gap is a question the archive should answer and does not, a citation
that opens the wrong page, or a wrong date. Paste the page URL: it carries the question and the filters.

## Pull requests

- Run the checks first: `python -m pytest`, and in `web/`, `npm run typecheck && npm test && npm run build`.
- Code is plain ASCII (no smart quotes, dashes or emoji), short and explicit.
- Answers must stay checkable. A change may not let an answer cite a page it did not retrieve, report
  text overlap as proof of support, or edit evaluation labels to improve a number.
- A change to search or to answers needs a measurement: run the benchmark (`scripts/v2/run_benchmark.py`)
  and put the numbers in the pull request.

## Conduct

Be respectful and specific. If something is unclear, open an issue and ask.

Maintainer: Jacob Ortiz, https://github.com/agentjakey. Contact: hello@archiveargues.org.
