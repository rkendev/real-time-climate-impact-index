#!/usr/bin/env bash
# Deterministic pre-deploy gate (UC-7, AT-9, NFR-C1). Phase 1 stub.
#
# The cheap deterministic check that must pass before any expensive cloud
# provisioning runs. In Phase 1 it confirms the local smoke marker exists;
# there is nothing to deploy yet, so with the marker absent it correctly
# refuses and exits non-zero. Later tracks produce the marker on a green smoke
# run, and Phase 2 extends this gate with the dependency and AWS-config checks.
set -euo pipefail

MARKER="${CII_SMOKE_MARKER:-.smoke_ok}"

if [[ ! -f "${MARKER}" ]]; then
  echo "pre-deploy gate FAILED: local smoke marker '${MARKER}' is absent." >&2
  echo "Run the local smoke check to green before deploying (NFR-C1)." >&2
  exit 1
fi

echo "pre-deploy gate OK: smoke marker '${MARKER}' present."
