#!/usr/bin/env bash
# Deterministic pre-deploy gate (UC-7, AT-9, NFR-C1).
#
# The cheap deterministic check that must pass before any expensive cloud
# provisioning runs. It confirms, in order:
#   1. the local smoke marker exists (gate G1, NFR-C1);
#   2. the dependency versions are single-sourced (INV-5, verify_versions);
#   3. the AWS Terraform config is present and valid: each stack initializes
#      offline and passes terraform validate, and declares its required
#      variables (AT-9).
# It refuses with a non-zero exit and names the failed check on any failure.
# Only on a full pass may the P2-T3 apply proceed. Nothing here provisions a
# resource or contacts AWS (terraform init runs with -backend=false).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MARKER="${CII_SMOKE_MARKER:-${REPO_ROOT}/.smoke_ok}"
INFRA_DIR="${CII_INFRA_DIR:-${REPO_ROOT}/infra}"
PYTHON="${CII_GATE_PYTHON:-python3}"
STACKS=(bootstrap persistent ephemeral)

fail() {
  echo "pre-deploy gate FAILED: $1" >&2
  exit 1
}

# The required variables each stack must declare for the P2-T3 apply.
required_vars_for() {
  case "$1" in
  bootstrap) echo "aws_region state_bucket project_tag" ;;
  persistent) echo "aws_region account_id project_tag iceberg_warehouse_bucket raw_s3_bucket dynamo_table notification_email" ;;
  ephemeral) echo "aws_region project_tag owner_ip ami_id processor_role_name" ;;
  esac
}

# 1. Local smoke marker (gate G1, NFR-C1).
if [[ ! -f "${MARKER}" ]]; then
  fail "local smoke marker '${MARKER}' is absent. Run the local smoke check to green before deploying."
fi

# 2. Dependency versions single-sourced (INV-5).
if ! "${PYTHON}" "${SCRIPT_DIR}/verify_versions.py" >/dev/null; then
  fail "dependency versions are not single-sourced (verify_versions)."
fi

# 3. AWS Terraform config present and valid (AT-9).
command -v terraform >/dev/null 2>&1 || fail "terraform is not installed."
for stack in "${STACKS[@]}"; do
  stack_dir="${INFRA_DIR}/${stack}"
  [[ -d "${stack_dir}" ]] || fail "Terraform stack directory '${stack_dir}' is missing."

  if ! terraform -chdir="${stack_dir}" init -backend=false -input=false >/dev/null 2>&1; then
    fail "terraform init failed for stack '${stack}'."
  fi
  if ! terraform -chdir="${stack_dir}" validate >/dev/null 2>&1; then
    fail "terraform validate failed for stack '${stack}'."
  fi

  for var in $(required_vars_for "${stack}"); do
    if ! grep -Eqs "variable[[:space:]]+\"${var}\"" "${stack_dir}"/*.tf; then
      fail "stack '${stack}' is missing required variable '${var}'."
    fi
  done
done

echo "pre-deploy gate OK: smoke marker present, versions single-sourced, AWS config valid."
