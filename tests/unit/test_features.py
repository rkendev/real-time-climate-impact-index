"""AT-3 (UC-3, FR-4, FR-5) and FR-9: component metrics, index, and label.

Fixed inputs produce the documented component metrics and an impact index within
0..100 matching hand-computed values, single-type windows still compute from the
available components (NFR-R4), and the verbal label maps by the configured bands.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from climate_index.core.features import (
    dryness_index,
    impact_index,
    pollution_index,
    temperature_anomaly,
    verbal_label,
)
from climate_index.core.models import SatelliteEvent, WeatherEvent

TS = datetime(2026, 7, 19, 12, 15, tzinfo=UTC)


def _weather(temperature_c: float, rainfall_mm: float) -> WeatherEvent:
    return WeatherEvent(
        ts=TS, region="EUR", temperature_c=temperature_c, rainfall_mm=rainfall_mm, wind_speed_ms=1.0
    )


def _satellite(
    cloud_cover_pct: float, vegetation_index: float, aerosol_index: float
) -> SatelliteEvent:
    return SatelliteEvent(
        ts=TS,
        region="EUR",
        cloud_cover_pct=cloud_cover_pct,
        vegetation_index=vegetation_index,
        aerosol_index=aerosol_index,
    )


# The AT-3 fixed scenario. EUR baseline is 12.0 (config).
_WEATHER = [_weather(20.0, 0.0), _weather(24.0, 10.0)]
_SATELLITE = [_satellite(50.0, 0.0, 1.0), _satellite(30.0, 0.2, 2.0)]


def test_temperature_anomaly_is_mean_minus_baseline() -> None:
    # mean temp 22.0 minus EUR baseline 12.0.
    assert temperature_anomaly(_WEATHER, "EUR") == pytest.approx(10.0)


def test_dryness_index_combines_rain_and_vegetation() -> None:
    # rain sub-score 1 - (5.0 / 20.0) = 0.75; veg sub-score (1 - 0.1) / 2 = 0.45.
    assert dryness_index(_WEATHER, _SATELLITE) == pytest.approx(0.60)


def test_pollution_index_combines_aerosol_and_cloud() -> None:
    # aerosol sub-score 1.5 / 2.0 = 0.75; cloud sub-score 40.0 / 100 = 0.40.
    assert pollution_index(_SATELLITE) == pytest.approx(0.575)


def test_impact_index_matches_hand_computed_value_and_is_in_range() -> None:
    anomaly = temperature_anomaly(_WEATHER, "EUR")
    dryness = dryness_index(_WEATHER, _SATELLITE)
    pollution = pollution_index(_SATELLITE)
    index = impact_index(anomaly, dryness, pollution)
    # 0.4*1.0 + 0.3*0.60 + 0.3*0.575 = 0.7525 -> 75.25.
    assert index == pytest.approx(75.25)
    assert 0.0 <= index <= 100.0


def test_components_are_bounded() -> None:
    assert 0.0 <= dryness_index(_WEATHER, _SATELLITE) <= 1.0
    assert 0.0 <= pollution_index(_SATELLITE) <= 1.0


def test_impact_index_clamps_to_range_on_extremes() -> None:
    # Very hot, bone dry, maximally polluted -> saturates at 100.
    assert impact_index(1000.0, 1.0, 1.0) == pytest.approx(100.0)
    # Cooler than baseline and clean -> floored at 0.
    assert impact_index(-50.0, 0.0, 0.0) == pytest.approx(0.0)


def test_dryness_from_weather_only_uses_rain_alone() -> None:
    # No satellite: dryness is the rainfall sub-score alone (single-type impute).
    assert dryness_index([_weather(20.0, 5.0)], []) == pytest.approx(0.75)


def test_pollution_without_satellite_imputes_zero() -> None:
    assert pollution_index([]) == pytest.approx(0.0)


def test_temperature_anomaly_without_weather_imputes_zero() -> None:
    assert temperature_anomaly([], "EUR") == pytest.approx(0.0)


def test_verbal_label_bands() -> None:
    # Config bands: low_max 33.34, medium_max 66.67.
    assert verbal_label(10.0) == "low"
    assert verbal_label(33.34) == "low"
    assert verbal_label(50.0) == "medium"
    assert verbal_label(66.67) == "medium"
    assert verbal_label(75.25) == "high"
    assert verbal_label(100.0) == "high"
