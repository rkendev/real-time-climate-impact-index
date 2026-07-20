"""INV-1 / ADR-0005: no real .tfvars is tracked, only *.tfvars.example placeholders.

Turns the .gitignore rule into a checked invariant. A real terraform.tfvars may
hold an account id, an owner IP, or a notification email; it must never be
committed. Only the placeholder *.tfvars.example files under infra/ are allowed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_real_tfvars_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "infra"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    offenders = [
        path
        for path in tracked
        if path.endswith(".tfvars") and not path.endswith(".tfvars.example")
    ]
    assert not offenders, f"real .tfvars tracked (must be git-ignored, INV-1): {offenders}"
