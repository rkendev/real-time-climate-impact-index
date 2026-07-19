"""AT-9 (UC-7, NFR-C1): the pre-deploy gate is meaningful end to end.

The cheap deterministic gate refuses to run when the local smoke marker is absent
and passes once a green smoke has written it. Both states are driven against the
committed ``scripts/pre_deploy_gate.sh`` with the marker redirected into tmp_path
(via CII_SMOKE_MARKER), so the repo marker is never touched.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "pre_deploy_gate.sh"


def _run_gate(marker: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CII_SMOKE_MARKER": str(marker)}
    return subprocess.run(
        ["bash", str(GATE)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_refuses_without_marker(tmp_path: Path) -> None:
    marker = tmp_path / ".smoke_ok"
    assert not marker.exists()

    result = _run_gate(marker, tmp_path)

    assert result.returncode != 0
    assert "absent" in result.stderr.lower()


def test_gate_passes_with_marker(tmp_path: Path) -> None:
    marker = tmp_path / ".smoke_ok"
    marker.write_text("ok\n", encoding="utf-8")

    result = _run_gate(marker, tmp_path)

    assert result.returncode == 0
    assert "OK" in result.stdout


def test_gate_passes_after_a_green_smoke_writes_the_marker(tmp_path: Path) -> None:
    # End to end: a green smoke writes the marker, and the gate then passes.
    marker = tmp_path / ".smoke_ok"
    env = {**os.environ, "CII_SMOKE_MARKER": str(marker), "PYTHONPATH": "src"}
    smoke = subprocess.run(
        [sys.executable, "-m", "climate_index.smoke"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stderr
    assert marker.exists()

    gate = _run_gate(marker, tmp_path)
    assert gate.returncode == 0
