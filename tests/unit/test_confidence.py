"""AT-4 (UC-3, NFR-DQ2): window composition maps to the confidence grade.

Both stream types present grade MEASURED, a single type grades INFERRED, and a
window below the sparsity threshold grades AMBIGUOUS regardless of composition.
"""

from __future__ import annotations

from climate_index.core.confidence import grade_confidence
from climate_index.core.models import Confidence


def test_both_types_present_is_measured() -> None:
    assert grade_confidence(weather_count=2, satellite_count=2) is Confidence.MEASURED


def test_weather_only_is_inferred() -> None:
    assert grade_confidence(weather_count=3, satellite_count=0) is Confidence.INFERRED


def test_satellite_only_is_inferred() -> None:
    assert grade_confidence(weather_count=0, satellite_count=3) is Confidence.INFERRED


def test_sparse_input_is_ambiguous() -> None:
    # Below sparsity_min_events (default 2), regardless of type.
    assert grade_confidence(weather_count=1, satellite_count=0) is Confidence.AMBIGUOUS


def test_empty_window_is_ambiguous() -> None:
    assert grade_confidence(weather_count=0, satellite_count=0) is Confidence.AMBIGUOUS


def test_sparsity_dominates_composition() -> None:
    # One weather and zero satellite is a single type, but too sparse to grade
    # anything but AMBIGUOUS. A single event never reaches MEASURED or INFERRED.
    assert grade_confidence(weather_count=1, satellite_count=0) is Confidence.AMBIGUOUS
