"""AT-9 / UC-7: the AWS pre-deploy gate refuses on any failed check and passes
only when every check is green.

Exercises the real scripts/pre_deploy_gate.sh as a subprocess against fixture
Terraform stacks (minimal, provider-free, so init and validate run instantly and
offline). Covers the marker-absent refusal, an invalid Terraform config, a
missing required variable, and the full green pass. The gate always runs the real
verify_versions against the real repo, which is single-sourced, so that check is
green throughout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "pre_deploy_gate.sh"

# The required variables per stack, mirroring the gate.
REQUIRED = {
    "bootstrap": ["aws_region", "state_bucket", "project_tag"],
    "persistent": [
        "aws_region",
        "account_id",
        "project_tag",
        "iceberg_warehouse_bucket",
        "raw_s3_bucket",
        "dynamo_table",
        "notification_email",
    ],
    "ephemeral": [
        "aws_region",
        "project_tag",
        "owner_ip",
        "ami_id",
        "processor_role_name",
        "ecr_repository_url",
        "image_tag",
    ],
}


def _write_stack(path: Path, var_names: list[str], extra_main: str = "") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.tf").write_text(
        'terraform {\n  required_version = ">= 1.10"\n}\n' + extra_main, encoding="utf-8"
    )
    body = "".join(f'variable "{name}" {{\n  type = string\n}}\n' for name in var_names)
    (path / "variables.tf").write_text(body, encoding="utf-8")


def _build_valid_infra(root: Path) -> Path:
    infra = root / "infra"
    for stack, var_names in REQUIRED.items():
        _write_stack(infra / stack, var_names)
    return infra


def _run_gate(infra_dir: Path, marker: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CII_INFRA_DIR"] = str(infra_dir)
    env["CII_SMOKE_MARKER"] = str(marker)
    env["CII_GATE_PYTHON"] = sys.executable
    return subprocess.run(["bash", str(GATE)], capture_output=True, text=True, env=env, check=False)


def _marker(root: Path) -> Path:
    marker = root / ".smoke_ok"
    marker.write_text("ok", encoding="utf-8")
    return marker


def test_refuses_without_smoke_marker(tmp_path: Path) -> None:
    infra = _build_valid_infra(tmp_path)
    result = _run_gate(infra, tmp_path / "absent-marker")
    assert result.returncode != 0
    assert "smoke marker" in result.stderr


def test_passes_on_full_green(tmp_path: Path) -> None:
    infra = _build_valid_infra(tmp_path)
    result = _run_gate(infra, _marker(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_refuses_on_invalid_terraform(tmp_path: Path) -> None:
    infra = _build_valid_infra(tmp_path)
    # Parseable but semantically invalid: a reference to an undeclared variable,
    # which init accepts and validate rejects.
    _write_stack(
        infra / "bootstrap",
        REQUIRED["bootstrap"],
        extra_main='output "bad" {\n  value = var.undeclared_xyz\n}\n',
    )
    result = _run_gate(infra, _marker(tmp_path))
    assert result.returncode != 0
    assert "validate" in result.stderr


def test_refuses_on_missing_required_variable(tmp_path: Path) -> None:
    infra = _build_valid_infra(tmp_path)
    # Valid config, but the bootstrap stack omits a required variable.
    _write_stack(infra / "bootstrap", ["aws_region", "state_bucket"])
    result = _run_gate(infra, _marker(tmp_path))
    assert result.returncode != 0
    assert "project_tag" in result.stderr
