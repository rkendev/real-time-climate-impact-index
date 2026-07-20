"""Offline Terraform proof: validate is clean, fmt is clean, and plan produces a
non-empty create plan with no AWS contact and no spend.

Runs against a temp copy of infra/ (so the repo tree stays clean) with dummy
credentials, the provider skip flags, and the AMI and cross-stack values supplied
as placeholder variables. The whole module skips when terraform is not installed
or its provider cannot be fetched (an offline environment), so the check never
produces a false failure.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from climate_index.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
STACKS = ["bootstrap", "persistent", "ephemeral"]
PLAN_STACKS = ["persistent", "ephemeral"]
PLAN_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
    "TF_VAR_project_tag": get_settings().project_tag,
}

_TERRAFORM = shutil.which("terraform")
pytestmark = pytest.mark.skipif(_TERRAFORM is None, reason="terraform is not installed")


def _terraform(*args: str, cwd: Path | None = None, env_extra: dict[str, str] | None = None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    argv = [str(_TERRAFORM), *args]
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, env=env, check=False)


@pytest.fixture(scope="module")
def infra(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    # Share one provider download across every stack, and keep it off the repo.
    cache = tmp_path_factory.mktemp("tf-plugin-cache")
    os.environ["TF_PLUGIN_CACHE_DIR"] = str(cache)

    root = tmp_path_factory.mktemp("infra-offline") / "infra"
    shutil.copytree(
        REPO_ROOT / "infra",
        root,
        ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", ".terraform.lock.hcl"),
    )

    # Probe once; skip the whole module if the provider cannot be fetched offline.
    probe = _terraform(
        "-chdir=" + str(root / "bootstrap"), "init", "-backend=false", "-input=false"
    )
    if probe.returncode != 0:
        os.environ.pop("TF_PLUGIN_CACHE_DIR", None)
        pytest.skip(f"terraform provider unavailable: {probe.stderr.strip()[:200]}")

    yield root
    os.environ.pop("TF_PLUGIN_CACHE_DIR", None)


def test_fmt_check_is_clean(infra: Path) -> None:
    result = _terraform("fmt", "-check", "-recursive", str(infra))
    assert result.returncode == 0, f"unformatted: {result.stdout}{result.stderr}"


@pytest.mark.parametrize("stack", STACKS)
def test_validate_is_clean(infra: Path, stack: str) -> None:
    chdir = "-chdir=" + str(infra / stack)
    assert _terraform(chdir, "init", "-backend=false", "-input=false").returncode == 0
    result = _terraform(chdir, "validate")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("stack", PLAN_STACKS)
def test_offline_plan_is_nonempty(infra: Path, stack: str) -> None:
    stack_dir = infra / stack
    override = stack_dir / "zz_local_backend_override.tf"
    override.write_text('terraform {\n  backend "local" {}\n}\n', encoding="utf-8")
    try:
        chdir = "-chdir=" + str(stack_dir)
        assert _terraform(chdir, "init", "-reconfigure", "-input=false").returncode == 0
        result = _terraform(
            chdir,
            "plan",
            "-input=false",
            "-var-file=terraform.tfvars.example",
            "-no-color",
            env_extra=PLAN_ENV,
        )
    finally:
        override.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    match = re.search(r"Plan:\s+(\d+) to add", result.stdout)
    assert match is not None, result.stdout
    assert int(match.group(1)) > 0, f"expected a non-empty create plan: {result.stdout}"
