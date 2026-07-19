# Canonical operator commands (FR-10, UC-6). Recipe lines are TAB-indented.
# PYTHONPATH=src and a .venv-based toolchain so no global tool is required.

PYTHON ?= python3.12
VENV := .venv
BIN := $(VENV)/bin
export PYTHONPATH := src

.PHONY: bootstrap hooks lint type-check test infra_up run_producer run_processor smoke ui

# Idempotent: safe to re-run. Creates the venv only if absent, asserts it is
# Python 3.12, installs pinned deps, wires the pre-commit git hook where the
# environment allows it, then runs the hygiene gate. The first gate run needs
# network to clone the hook repos; after that they are cached.
bootstrap:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(BIN)/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "venv interpreter is not Python 3.12: %s" % sys.version'
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt -r requirements-dev.txt
	$(MAKE) hooks
	PATH="$(CURDIR)/$(BIN):$$PATH" bash scripts/verify-precommit.sh

# Wire the pre-commit git-hook shim. Skipped (not failed) only when the
# environment sets core.hooksPath, which makes pre-commit refuse the shim; the
# hygiene gate in bootstrap still validates and runs every hook regardless, so
# no hook-install failure is ever swallowed.
hooks:
	@if [ -n "$$(git config core.hooksPath 2>/dev/null)" ]; then \
		echo "note: git core.hooksPath is set; skipping the pre-commit git-hook shim (the hygiene gate still runs all hooks)."; \
	else \
		$(BIN)/pre-commit install; \
	fi

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

type-check:
	$(BIN)/mypy src

test:
	$(BIN)/pytest

# Run the producer against the Kafka adapter path (UC-1). No-op-safe without a
# broker: with CII_TRANSPORT_BOOTSTRAP_SERVERS unset it logs and exits without
# importing the Kafka client. The in-memory path is exercised by the tests.
run_producer:
	$(BIN)/python -m climate_index.producer

# Run the processor on the in-memory path (UC-3, UC-4). Populates a MemoryTransport
# via the producer, windows the validated events, and writes aggregates and raw
# events through the DuckDB stores. Needs no broker (local-first). The live Kafka
# consumer loop arrives in the infra track.
run_processor:
	$(BIN)/python -m climate_index.processor

# Stubs: the targets must exist (FR-10); implementations arrive in later tracks.
infra_up smoke ui:
	@echo "$@: not implemented until a later track"

