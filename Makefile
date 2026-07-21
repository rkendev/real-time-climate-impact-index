# Canonical operator commands (FR-10, UC-6). Recipe lines are TAB-indented.
# PYTHONPATH=src and a .venv-based toolchain so no global tool is required.

PYTHON ?= python3.12
VENV := .venv
BIN := $(VENV)/bin
export PYTHONPATH := src

.PHONY: bootstrap hooks lint type-check test infra_up run_producer run_processor smoke ui \
	tf-fmt tf-validate tf-plan teardown-audit pre-deploy-gate container-smoke \
	image-build image-push verify-at5 verify-nfr-p3 \
	vps-demo-up vps-demo-down vps-demo-refresh vps-demo-status

# Dummy credentials and provider skip flags let terraform validate and plan run
# with zero AWS contact and zero spend. TF_STACKS is the full set; TF_PLAN_STACKS
# omits bootstrap (validated only; it is applied once to stand up remote state).
TF ?= terraform
TF_STACKS := bootstrap persistent ephemeral
TF_PLAN_STACKS := persistent ephemeral
TF_PLAN_ENV := AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_DEFAULT_REGION=us-east-1

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
	$(BIN)/mypy src scripts/teardown_audit.py scripts/verify_at5_glue.py scripts/verify_nfr_p3.py \
		deploy/vps/feed_history.py deploy/vps/publish_snapshot.py

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

# End-to-end local smoke on the in-memory path (UC-6, FR-7, FR-10, no Kafka).
# Produces a small batch, runs the pipeline, and asserts the aggregate store is
# non-empty and duplicate-free and that raw counts equal produced minus
# quarantined counts. On green it writes the local smoke marker the pre-deploy
# gate checks; on a broken pipeline it exits non-zero.
smoke:
	$(BIN)/python -m climate_index.smoke

# Open the read-only dashboard (UC-5, FR-8, FR-10). Reads the aggregate store
# seeded by run_processor; performs no computation and no writes (INV-2).
ui:
	$(BIN)/streamlit run app/dashboard.py

# End-to-end container smoke through a live Kafka broker (UC-6, FR-6, FR-7). Builds
# the app image, runs producer to consumer to store to dashboard on the local
# backend, and asserts the aggregate is non-empty and duplicate-free. Exercises
# the live-broker path the in-memory smoke cannot; no AWS, no spend.
container-smoke:
	bash scripts/container_smoke.sh

# Formatting gate for the .tf files (kept green alongside the Python gates).
tf-fmt:
	$(TF) fmt -check -recursive infra

# Offline, credential-free validate across all three stacks (init -backend=false
# so no state bucket is needed and no AWS is contacted).
tf-validate:
	@for stack in $(TF_STACKS); do \
		echo "== validate: $$stack =="; \
		$(TF) -chdir=infra/$$stack init -backend=false -input=false >/dev/null || exit 1; \
		$(TF) -chdir=infra/$$stack validate || exit 1; \
	done

# Offline, credential-free create plan on the billing stacks. A throwaway local
# backend override lets plan run without the real S3 backend; project_tag is
# injected from config so the plan tags match the teardown audit. No AWS contact,
# no spend. The placeholder tfvars.example supplies the remaining values.
tf-plan:
	@tag=$$($(BIN)/python -c 'from climate_index.config import get_settings; print(get_settings().project_tag)'); \
	for stack in $(TF_PLAN_STACKS); do \
		echo "== plan: $$stack =="; \
		dir=infra/$$stack; ovr=$$dir/zz_local_backend_override.tf; \
		printf 'terraform {\n  backend "local" {}\n}\n' > $$ovr; \
		$(TF) -chdir=$$dir init -reconfigure -input=false >/dev/null || { rm -f $$ovr; exit 1; }; \
		$(TF_PLAN_ENV) TF_VAR_project_tag=$$tag \
			$(TF) -chdir=$$dir plan -input=false -var-file=terraform.tfvars.example; \
		rc=$$?; rm -f $$ovr; [ $$rc -eq 0 ] || exit $$rc; \
	done

# Build the one app image for the t4g box (ADR-0006). The box is arm64 (Graviton)
# while the build host is x86_64, so the image MUST be built for linux/arm64 or it
# fails at boot with an exec-format error. ECR_REPO is the repository URL from the
# persistent stack output; IMAGE_TAG defaults to the short git sha. This is a
# paid-window step (the artifact the box pulls); building itself does not spend.
IMAGE_TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

image-build:
	@test -n "$(ECR_REPO)" || { echo "set ECR_REPO=<ecr repository url> (terraform output ecr_repository_url)"; exit 2; }
	docker buildx build --platform linux/arm64 -t $(ECR_REPO):$(IMAGE_TAG) --load .

# Push the arm64 image to ECR. Logs in with the operator workstation credentials
# (never the box), deriving the registry host and region from ECR_REPO, then builds
# and pushes for arm64 in one step. The box pulls this image via its instance role.
image-push:
	@test -n "$(ECR_REPO)" || { echo "set ECR_REPO=<ecr repository url> (terraform output ecr_repository_url)"; exit 2; }
	@registry=$$(echo "$(ECR_REPO)" | cut -d/ -f1); \
	region=$$(echo "$$registry" | cut -d. -f4); \
	aws ecr get-login-password --region "$$region" | docker login --username AWS --password-stdin "$$registry"; \
	docker buildx build --platform linux/arm64 -t $(ECR_REPO):$(IMAGE_TAG) --push .

# Paid-window verifications (exit gate G2). Both require the AWS backend and run
# against real AWS; the measurement logic is unit-tested offline. AT-5 replays a
# window and asserts exactly one Iceberg row against the real Glue catalog; NFR-P3
# seeds a full day of windows and asserts the DynamoDB read p95 is under one second.
verify-at5:
	$(BIN)/python scripts/verify_at5_glue.py

verify-nfr-p3:
	$(BIN)/python scripts/verify_nfr_p3.py

# Tag-based teardown audit (AT-11). Region, tag, and the optional endpoint come
# from config. The real post-teardown run is P2-T3; the moto test proves it here.
teardown-audit:
	$(BIN)/python scripts/teardown_audit.py

# Deterministic pre-deploy gate (AT-9, UC-7). Must pass before any P2-T3 apply.
pre-deploy-gate:
	CII_GATE_PYTHON=$(BIN)/python bash scripts/pre_deploy_gate.sh

# The cloud lifecycle (FR-10). The gated apply, run, verify, and teardown is the
# one spend step of P2-T3 (exit gate G2); it is documented here but deliberately
# not wired to run. The manual sequence, after a green pre-deploy-gate:
#   1. terraform -chdir=infra/bootstrap apply           (one time, stands up state)
#   2. terraform -chdir=infra/persistent init -backend-config=... && apply
#   3. terraform -chdir=infra/ephemeral  init -backend-config=... && apply
#   4. run the pipeline, confirm the dashboard within NFR-P3
#   5. terraform -chdir=infra/ephemeral destroy && make teardown-audit
infra_up:
	@echo "$@: run 'make pre-deploy-gate' then the documented P2-T3 apply sequence (gate G2)."

# The always-on local live demo (RUNBOOK: "Local live demo"). Entirely the local
# backend: no cloud credential is read, no cloud call is made, no cost. Standing it
# up installs two units and one Caddy site block on the host, so these targets are
# operator steps, not part of any gate.
DEMO := deploy/vps

# Stand the demo up (idempotent): git-ignored environment, derived host, rendered
# units, one refresh, the timer, and the site block on the existing Caddy.
vps-demo-up:
	bash $(DEMO)/install.sh

# Take it down: units removed, site block removed, refresh stack down with its
# volume. Add ARGS=--purge to drop the served snapshot too.
vps-demo-down:
	bash $(DEMO)/uninstall.sh $(ARGS)

# Run one refresh now (the same bounded pipeline the timer drives).
vps-demo-refresh:
	bash $(DEMO)/refresh.sh

# What is resident, when the next refresh fires, and how fresh the snapshot is.
vps-demo-status:
	@systemctl --no-pager --lines=0 status climate-index-dashboard.service | head -4 || true
	@systemctl list-timers --no-pager climate-index-refresh.timer || true
	@echo "== containers in the demo project (expected: none between refreshes) =="
	@docker ps --filter "label=com.docker.compose.project=$${CII_DEMO_COMPOSE_PROJECT:-cii-demo}" \
		--format '{{.Names}}\t{{.Status}}' || true
	@echo "== served snapshot =="
	@set -a; . $(DEMO)/demo.env; set +a; \
		ls -l "$$CII_DEMO_DATA_DIR/aggregates.duckdb" 2>/dev/null || echo "no snapshot published yet"

