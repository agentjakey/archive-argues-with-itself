# archive-argues-with-itself

An open-source civic-memory tool over Canadian government public-health
publications held by the Internet Archive. It answers civic questions from
page-level evidence, compares how the record describes an issue across decades,
and makes coverage gaps and OCR uncertainty visible. It is not a chatbot:
provenance, coverage, and uncertainty are prioritized over fluency, every claim
carries a page-level citation, and the tool never claims to reach the present
(the pilot corpus is ~1960-2009). Scope is fixed by `docs/PROPOSAL.md`.

## Current state

| Stage | Status | Output |
| --- | --- | --- |
| Harvest (IA metadata + OCR) | done | 3,477 Canadian-government texts (DjVu XML) under `raw/` |
| Load + parse | done | 468,405 pages / 745,893 passages in `civic.db` |
| Normalize + coverage | done | date / jurisdiction / issuer / doc_type + 1,075 coverage cells |
| Hybrid index | done | `index/vectors.db` (BM25 + 384-dim dense) |
| Page-level citations + verifier | done | fixed IA deep links + deterministic 3-check verifier |
| Evaluation | done | 50 human-labeled questions; `reports/phase7/eval_report.md` |
| Synthesis (`generate/`) | done | cited answers with code-decided abstention; deterministic citation verification |
| Read-only API (`api/`) | done | FastAPI `/ask`, `/examples`, `/health` |
| Web UI (`web/`) | done | reading-room evidence trail: answer with page-level citation chips, abstention card, decade timeline, page drawer, compare view; kiosk mode |

## Quickstart

Python 3.11 (`requires-python = ">=3.11,<3.12"`).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest        # hermetic: no network, no model, no index
```

For synthesis, copy `.env.example` to `.env` and put your key in `ANTHROPIC_API_KEY`,
or set `ANTHROPIC_API_KEY` in the environment. The key is never committed.

## Reproduce

Commands use the venv interpreter and default to `--config config/pilot.toml`.
Only step 1 touches the network (Internet Archive); everything after runs offline
from `raw/` and `civic.db`.

```powershell
# 1. Harvest: manifest, per-item metadata, and OCR derivatives into raw/
python -m archive_debugger.harvest.fetch --download-all --contact you@example.com

# 2. Ingest: load raw items, then parse cached OCR into pages and passages
python -m archive_debugger.ingest.loader
python -m archive_debugger.ingest.build --fresh

# 3. Normalize dates / jurisdiction / issuer / doc_type and build coverage cells
python -m archive_debugger.ingest.normalize

# 4. Build the dense vector index (one-time, ~45-90 min on CPU, resumable)
python -m archive_debugger.retrieve.index

# 5. Evaluate: load questions, apply the committed gold labels, score
python -m archive_debugger.eval.questions --file eval/seed_questions.jsonl
python -m archive_debugger.eval.assist                       # writes the retrieval worksheet
python -m archive_debugger.eval.label --from-worksheet reports/phase7/label_worksheet.jsonl --apply-decisions eval/gold_decisions.json
python -m archive_debugger.eval.report                       # -> reports/phase7/
```

### Serve (read-only API)

```powershell
# Windows, no make needed:
.\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
```

`GET /health`, `GET /examples` (seed questions with gold verdicts), `POST /ask`
`{question, filters?, provider?, model?}` -> `{answer, evidence}`. Set
`ALLOWED_ORIGINS` (comma-separated) to enable CORS; unset means same-origin only.
When `web/dist` exists it is served at `/` with an `index.html` fallback.

### Web app (`web/`)

Vite + React + TypeScript + Tailwind; no router, no state library. Node 20 LTS
(`web/.nvmrc`); `web/dist` is a build artifact and is not committed.

```powershell
cd web
npm ci                     # reproducible install from package-lock.json
npm run typecheck          # tsc --noEmit
npm test                   # vitest
npm run build              # -> web/dist, served by the API at /
npm run dev                # dev server on http://127.0.0.1:5173 proxying /ask /examples /health to :8000
```

To view the built app, start the API (previous section) and open
`http://127.0.0.1:8000/`. Append `?kiosk=1` for the exhibit mode (larger type,
filters hidden, QR placeholder). `VITE_API_BASE` points the app at a remote API;
empty means same-origin.

### Scope is config-driven

The pilot corpus is defined entirely by `config/pilot.toml`: topic term-set,
Internet Archive collection clause, binning window, and usable-item floor. The
resulting item set is recorded in `data/manifest/` (IA identifiers plus the exact
scope query) so anyone can re-download the same items. Another topic (for example
housing) is a new config plus a new manifest, not a code change.

### Data artifacts are not in the repo

`raw/` (harvested OCR), `civic.db` (parsed and normalized corpus), and
`index/vectors.db` (dense vectors) are git-ignored and rebuilt with the commands
above. The reproducible gold -- `eval/seed_questions.jsonl` and
`eval/gold_decisions.json` -- is committed, as is `data/manifest/`.

## Architecture

Layers are separated by a load-bearing network boundary: only `harvest/` reaches
the Internet Archive.

- `harvest/` -- network layer; caches IA metadata and OCR under `raw/`.
- `ingest/` -- local parse, normalize, and `civic.db` build.
- `retrieve/` -- hybrid retrieval and page-level citations (`citation.py` is the
  single source of the deep-link format and the 3-check verifier).
- `generate/` -- synthesis grounded strictly in retrieved passages *(planned;
  config-driven external LLM, isolated, stubbed in tests)*.
- `eval/` -- retrieval evaluation against human gold labels.
- `api/`, `web/` -- read-only serve layer and Next.js interface *(planned)*.

### Retrieval

BM25 over an FTS5 index fused with dense cosine search via Reciprocal Rank Fusion
(k=60), a soft OCR-quality down-weight, and composable pre-filters (period /
jurisdiction / doc_type / min-OCR). Dense vectors use
`paraphrase-multilingual-MiniLM-L12-v2` (384-dim, EN/FR) in a standalone
`index/vectors.db` via sqlite-vec (flat, exact). Every result carries page-level
provenance and the deep link
`https://archive.org/details/{item_id}/page/n{leaf_index}`; no coordinates are
stored.

### Evaluation

Gold labels are human judgments (relevance per candidate; answerable or
should-abstain per question) and are never inferred by the tool; see
`eval/labeling_notes.md` for the labeling rule and methods. Metrics are pooled
recall@k and nDCG@10 over the judged pool plus an abstention-leakage view.
Automated citation checking is a deterministic 3-check verifier (passage exists /
was in the retrieved evidence / resolves to a real page); citation *support* is a
manual audit, never an overlap score.

## Layout

```
config/pilot.toml          pilot scope, window, retrieval and eval settings
data/manifest/             committed corpus manifest (IA identifiers + scope query)
docs/PROPOSAL.md           submitted proposal (source of truth for scope)
eval/                      seed questions, gold decisions, labeling notes
src/archive_debugger/      harvest / ingest / retrieve / generate / eval / api
tests/                     hermetic pytest suite (tests/fixtures/ holds real fixtures)
reports/                   coverage audit and the eval summary
web/                       Next.js read-only interface (planned)
```

## License

MIT. See `LICENSE` and `CITATION.cff`.
