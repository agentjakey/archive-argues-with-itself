# Archive Argues With Itself

[![CI](https://github.com/agentjakey/archive-argues-with-itself/actions/workflows/ci.yml/badge.svg)](https://github.com/agentjakey/archive-argues-with-itself/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](pyproject.toml)
[![Node 20](https://img.shields.io/badge/node-20-blue.svg)](web/.nvmrc)
[![Data release](https://img.shields.io/github/v/release/agentjakey/archive-argues-with-itself?filter=data-*&label=data%20release)](https://github.com/agentjakey/archive-argues-with-itself/releases)

The public record disagrees with itself across decades. This tool shows you the pages.

Ask a civic question about Canadian government public-health publications (1960 to
2009, held by the Internet Archive) and get the scanned pages that bear on it, an
answer in which every sentence cites a page, a timeline of what the record holds
by decade, and a plain statement when the record is too thin to answer.

![Answer with page-level citations and the evidence trail](docs/images/hero.png)

**Try it:** LIVE_URL

## What it is, and is not

It is a civic memory debugger: page-level provenance on every claim, a comparison
view for how official language changes between decades, and a coverage view that
shows where the archive is silent or undated. It is not a chatbot. Provenance,
coverage and uncertainty are ranked above fluency; the model may only write
sentences it can cite to a retrieved page, and the tool abstains when the
evidence is thin. It never claims to reach the present: scanned government
publications with OCR effectively stop around 2009.

| Abstention with the coverage grid | Two pages, decades apart |
| --- | --- |
| ![Abstention card and coverage grid](docs/images/abstention.png) | ![Compare view](docs/images/compare.png) |

## The numbers

Measured on an audit run of all 50 evaluation questions with the shipped
configuration; judgments and labels by the author. Details and every source file
in [`reports/phase16/audit_report.md`](reports/phase16/audit_report.md).

| what | value | where |
| --- | --- | --- |
| Citation support, strict: every claim in the sentence appears in the cited page (178 kept sentences on the 35 answerable questions) | 93.3% | [audit report](reports/phase16/audit_report.md), [judgments](eval/judgments_phase16.json) |
| Citation support, lenient: supported or partly supported (same 178 sentences) | 99.4% | [audit report](reports/phase16/audit_report.md) |
| Cited passages that resolve to a recorded page | 119/119 | [audit report](reports/phase16/audit_report.md) |
| Abstention on questions the archive cannot answer | 10/15 in-sample; 9/10 held out | [audit report](reports/phase16/audit_report.md), [held-out run](reports/phase16/holdout_run.md) |
| False abstention on answerable questions | 0/35 in-sample; 1/5 held out | [audit report](reports/phase16/audit_report.md), [held-out run](reports/phase16/holdout_run.md) |
| Retrieval recall@10 on the fully judged gold, before and after the retrieval changes | 0.347 to 0.458 | [retrieval report](reports/phase13/retrieval_report.md) |

Read these with two caveats stated in the reports: the abstention rule was
amended once against the same 50 questions (the held-out set is the exception),
and the candidate labels behind the gold extension and the sentence judgments
were first proposed by an assistant model of the same family that writes the
answers, then decided by the author.

## Quickstart

Python 3.11 (`requires-python = ">=3.11,<3.12"`).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest        # hermetic: no network, no model, no index
```

For synthesis, copy `.env.example` to `.env` and fill in the API key line. The key
is never committed.

## Run it yourself

Two ways to get the corpus database and the dense index (about 3.2 GiB).

**Fast path: download the data release** and verify the checksums:

```powershell
$R = "https://github.com/agentjakey/archive-argues-with-itself/releases/download/data-v1"
New-Item -ItemType Directory -Force C:\civic-data\index | Out-Null
curl.exe -L -o C:\civic-data\civic.db            "$R/civic.db"
curl.exe -L -o C:\civic-data\index\vectors.db    "$R/vectors.db"
curl.exe -L -o C:\civic-data\data-release.sha256 "$R/data-release.sha256"
# verify (Git Bash): cd /c/civic-data && sha256sum -c data-release.sha256   (vectors.db is under index/)
```

Put `CIVIC_DB_PATH=C:\civic-data\civic.db` and
`CIVIC_INDEX_PATH=C:\civic-data\index\vectors.db` in `.env` (keep the files out of
synced folders), build the web app once, and serve:

```powershell
cd web; npm ci; npm run build; cd ..
.\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. `?kiosk=1` is the exhibit mode; see
[`docs/DEMO.md`](docs/DEMO.md) for the unattended, offline setup and
[`docs/DEPLOY.md`](docs/DEPLOY.md) to host it (one Docker image that downloads the
release on first boot; Railway steps; any Docker host).

**Reproducible path: rebuild from the manifest.** The item set is fixed by
[`data/manifest/`](data/manifest/); the rebuild yields the same corpus, and the
dense index is deterministic for the pinned model. Only step 1 touches the
network.

```powershell
python -m archive_debugger.harvest.fetch --download-all --contact you@example.com   # 1. cache metadata + OCR under raw/
python -m archive_debugger.ingest.loader                                              # 2. load items
python -m archive_debugger.ingest.build --fresh                                       #    parse OCR into pages and passages
python -m archive_debugger.ingest.normalize                                           # 3. dates, jurisdiction, issuer, doc type
python -m archive_debugger.ingest.sections                                            #    front / body / back page classes
python -m archive_debugger.retrieve.index                                             # 4. dense index (45-90 min on CPU)
python -m archive_debugger.eval.questions --file eval/seed_questions.jsonl            # 5. evaluation questions and gold
python -m archive_debugger.eval.label --from-worksheet reports/phase7/label_worksheet.jsonl --apply-decisions eval/gold_decisions.json
python -m archive_debugger.eval.report
```

## The four rules

Every phase of the work was bound by four rules that never moved. The only
network call outside the harvest layer is the configured language-model API;
nothing downstream re-fetches the archive. Citation verification is three
structural checks (the cited passage exists, it was in the evidence retrieved for
that question, it resolves to a recorded page) and text overlap is never reported
as correctness. Citations are page-level deep links of one fixed form, with no
coordinate storage. Evaluation gold is never edited to improve a run;
configuration changes are logged in `eval_runs`, and gold extensions are additive
and recorded with who decided what.

## Methods and gaps

- [`docs/METHODS.md`](docs/METHODS.md): how the corpus was chosen, parsed,
  indexed, retrieved, cited and measured, every number tied to its report file.
- [`docs/GAP_REPORT.md`](docs/GAP_REPORT.md): what the archive cannot tell you
  (45% undated passages, no record after 2009, front-matter pollution, metadata
  dates that disagree with the text, why housing was not the pilot, what the
  abstention sweeps showed, why verification checks support and not relevance).
- [`CHANGELOG.md`](CHANGELOG.md): one entry per phase, from the reports.
- The same content is in the app under "How this works" and "Gaps".

## How it works, briefly

`harvest/` caches Internet Archive metadata and existing OCR derivatives.
`ingest/` parses them into a SQLite database of items, pages and passages, fills
dates, jurisdiction, issuer and document type without imputation, and classifies
front and back matter. `retrieve/` fuses BM25 and dense cosine search (384-dim
multilingual MiniLM in sqlite-vec) with Reciprocal Rank Fusion, a soft OCR
down-weight, front/back demotion and a per-item cap, and attaches page-level
provenance to every hit. `generate/` drafts cited sentences with the configured
model, verifies each citation with the three checks, drops what fails, and
abstains by rule when the record is thin. `eval/` scores retrieval against human
labels and holds the labeling tools. `api/` is a read-only FastAPI layer with an
answer cache; `web/` is the Vite + React interface. Layout: `src/archive_debugger/`
(one package per layer), `web/`, `config/`, `eval/`, `reports/`, `docs/`, `scripts/`.

## Contributing

Issues are welcome, especially corpus gaps: a question the archive should answer
and does not, a page that resolves to the wrong scan, a date the metadata gets
wrong. Use the issue templates. To add a second scope (another topic or
jurisdiction), write a new `config/pilot.toml` (query, collections, window) and a
new `data/manifest/`; the code does not change. Run the audit method first: the
British Columbia sizing in [`reports/bc_audit/bc_sizing.md`](reports/bc_audit/bc_sizing.md)
shows what a scope that does not clear the floor looks like. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Acknowledgements

Built during the AI Builders Fellowship of the BC + AI Ecosystem, with the
Internet Archive, whose collections, OCR and page images make the tool possible.
Page images are served by archive.org and are not redistributed here. The
publications are Canadian government documents and remain under their own terms.

## Citation

See [`CITATION.cff`](CITATION.cff). Author: Jacob Ortiz.

## License

MIT. See [`LICENSE`](LICENSE).
