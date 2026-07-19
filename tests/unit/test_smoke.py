"""End-to-end smoke and marker (UC-6, FR-7, FR-10, NFR-C1).

run_smoke produces a batch on the in-memory path, runs the pipeline, and asserts
the aggregate store is non-empty and duplicate-free and that raw counts equal
produced minus quarantined counts (FR-7). On green it writes the marker the
pre-deploy gate checks. The marker path is redirected into tmp_path so the real
repo marker is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from climate_index.smoke import SmokeResult, run_smoke


def _redirect_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    marker = tmp_path / ".smoke_ok"
    monkeypatch.setenv("CII_SMOKE_MARKER", str(marker))
    return marker


def test_run_smoke_is_non_empty_and_duplicate_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _redirect_marker(monkeypatch, tmp_path)

    result = run_smoke(ticks=3)

    assert isinstance(result, SmokeResult)
    assert result.aggregate_rows > 0  # non-empty
    assert result.produced > 0


def test_run_smoke_holds_the_fr7_raw_relationship(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _redirect_marker(monkeypatch, tmp_path)

    result = run_smoke(ticks=2)

    # FR-7: raw counts equal produced minus quarantined counts. The smoke injects
    # exactly one malformed message, so one event is quarantined and never stored.
    assert result.quarantined == 1
    assert result.raw_count == result.consumed - result.quarantined
    assert result.raw_count == result.produced


def test_run_smoke_writes_the_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    marker = _redirect_marker(monkeypatch, tmp_path)
    assert not marker.exists()

    run_smoke(ticks=1)

    assert marker.exists()
    assert marker.read_text(encoding="utf-8").strip() == "ok"
