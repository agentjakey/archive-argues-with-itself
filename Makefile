# Makefile for archive-argues-with-itself.
#
# Layer separation is enforced by which target may touch the network:
#   harvest -> network (Internet Archive) only.
#   index / eval / serve -> local only, no network.
#
# Targets currently print a not-implemented notice. They name the entry points
# that the corresponding layers will expose; wiring lands in later phases.

PYTHON ?= python
CONFIG ?= config/pilot.toml

.PHONY: help install install-web harvest index eval serve web test

help:
	@echo "Targets:"
	@echo "  install      install the python package with dev extras"
	@echo "  install-web  install web/ node dependencies"
	@echo "  harvest      collect IA metadata + OCR into raw/ (network layer)"
	@echo "  index        parse, normalize, and build the hybrid index (local)"
	@echo "  eval         run retrieval + citation-support evaluation (local)"
	@echo "  serve        run the read-only api over the built index (local)"
	@echo "  web          run the Next.js interface in web/ (dev)"
	@echo "  test         run pytest"

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-web:
	cd web && npm install

harvest:
	@echo "harvest: not implemented yet -> src/archive_debugger/harvest (config: $(CONFIG))"

index:
	@echo "index: not implemented yet -> src/archive_debugger/ingest"

eval:
	@echo "eval: not implemented yet -> src/archive_debugger/eval"

serve:
	@echo "serve: not implemented yet -> src/archive_debugger/api (read-only)"

web:
	cd web && npm run dev

test:
	$(PYTHON) -m pytest
