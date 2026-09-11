# Makefile for archive-argues-with-itself.
#
# Layer separation is enforced by which target may touch the network:
#   harvest -> network (Internet Archive) only.
#   ingest / index / eval / serve -> local only, no network (serve calls the configured model API).

PYTHON ?= python
CONFIG ?= config/pilot.toml
CONTACT ?=
BASE_URL ?= http://127.0.0.1:8000

.PHONY: help install install-web web-install web-build harvest ingest index eval serve web smoke test

help:
	@echo "Targets:"
	@echo "  install      install the python package with dev extras"
	@echo "  install-web  install web/ node dependencies"
	@echo "  web-build    typecheck, test, and build the web app into web/dist"
	@echo "  harvest      collect IA metadata + OCR into raw/ (network layer; needs CONTACT=you@example.com)"
	@echo "  ingest       load items, parse OCR, normalize, classify front/back matter (local)"
	@echo "  index        build the dense vector index (local, one-time)"
	@echo "  eval         load questions, apply the committed gold labels, score (local)"
	@echo "  serve        run the read-only api over the built index"
	@echo "  web          run the Vite dev server in web/"
	@echo "  smoke        smoke-test a running api (BASE_URL=...)"
	@echo "  test         run pytest"

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-web web-install:
	cd web && npm ci

web-build:
	cd web && npm run typecheck && npm test && npm run build

harvest:
	$(PYTHON) -m archive_debugger.harvest.fetch --config $(CONFIG) --download-all --contact "$(CONTACT)"

ingest:
	$(PYTHON) -m archive_debugger.ingest.loader --config $(CONFIG)
	$(PYTHON) -m archive_debugger.ingest.build --config $(CONFIG) --fresh
	$(PYTHON) -m archive_debugger.ingest.normalize --config $(CONFIG)
	$(PYTHON) -m archive_debugger.ingest.sections --config $(CONFIG)

index:
	$(PYTHON) -m archive_debugger.retrieve.index --config $(CONFIG)

eval:
	$(PYTHON) -m archive_debugger.eval.questions --config $(CONFIG) --file eval/seed_questions.jsonl
	$(PYTHON) -m archive_debugger.eval.label --config $(CONFIG) --from-worksheet reports/phase7/label_worksheet.jsonl --apply-decisions eval/gold_decisions.json
	$(PYTHON) -m archive_debugger.eval.report --config $(CONFIG)

serve:
	$(PYTHON) -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000

web:
	cd web && npm run dev

smoke:
	$(PYTHON) scripts/smoke.py $(BASE_URL)

test:
	$(PYTHON) -m pytest
