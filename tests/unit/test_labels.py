"""FR-9: verbal-label band mapping (display-safe module).

The label maps a stored impact index to low/medium/high by the configured
thresholds. This is the FR-9 threshold unit test; it lives with the display-safe
:mod:`climate_index.labels` module rather than the compute core (INV-2, AT-6).
"""

from __future__ import annotations

from climate_index.labels import verbal_label


def test_verbal_label_bands() -> None:
    # Config bands: low_max 33.34, medium_max 66.67.
    assert verbal_label(10.0) == "low"
    assert verbal_label(33.34) == "low"
    assert verbal_label(50.0) == "medium"
    assert verbal_label(66.67) == "medium"
    assert verbal_label(75.25) == "high"
    assert verbal_label(100.0) == "high"


def test_boundaries_are_inclusive_lower_bands() -> None:
    # A value just above a boundary crosses into the next band.
    assert verbal_label(33.35) == "medium"
    assert verbal_label(66.68) == "high"
