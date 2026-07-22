"""AT-3 (UC-3, FR-4, FR-5): component metrics and index.

Fixed inputs produce the documented component metrics and an impact index within
0..100 matching hand-computed values, and single-type windows still compute from
the available components (NFR-R4). The verbal-label mapping (FR-9) is display
formatting and is tested in ``test_labels.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from climate_index.core.features import (
    dryness_index,
    impact_index,
    pollution_index,
    temperature_anomaly,
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


# The AT-3 fixed scenario. TS is in July, so the EUR normal in play is the July
# one, 21.1 (config region_monthly_baselines, index 6). The spec takes the month
# from the window start, so these direct calls pass it explicitly.
_JULY = TS.month
_WEATHER = [_weather(20.0, 0.0), _weather(24.0, 10.0)]
_SATELLITE = [_satellite(50.0, 0.0, 1.0), _satellite(30.0, 0.2, 2.0)]


def test_temperature_anomaly_is_mean_minus_the_month_normal() -> None:
    # mean temp 22.0 minus the EUR July normal 21.1.
    assert temperature_anomaly(_WEATHER, "EUR", _JULY) == pytest.approx(0.9)


def test_temperature_anomaly_follows_the_month_it_is_given() -> None:
    """The same readings are a mild July but a very warm January (E-7).

    This is the point of monthly normals: against one annual scalar, every
    summer window in a seasonal region would report a large positive anomaly
    purely because it is summer.
    """
    january = temperature_anomaly(_WEATHER, "EUR", 1)
    july = temperature_anomaly(_WEATHER, "EUR", 7)
    assert january == pytest.approx(22.0 - 3.1)
    assert july == pytest.approx(22.0 - 21.1)
    assert january > july


def test_dryness_index_combines_rain_and_vegetation() -> None:
    # rain sub-score 1 - (5.0 / 20.0) = 0.75; veg sub-score (1 - 0.1) / 2 = 0.45.
    assert dryness_index(_WEATHER, _SATELLITE) == pytest.approx(0.60)


def test_pollution_index_combines_aerosol_and_cloud() -> None:
    # aerosol sub-score 1.5 / 2.0 = 0.75; cloud sub-score 40.0 / 100 = 0.40.
    assert pollution_index(_SATELLITE) == pytest.approx(0.575)


def test_impact_index_matches_hand_computed_value_and_is_in_range() -> None:
    anomaly = temperature_anomaly(_WEATHER, "EUR", _JULY)
    dryness = dryness_index(_WEATHER, _SATELLITE)
    pollution = pollution_index(_SATELLITE)
    index = impact_index(anomaly, dryness, pollution)
    # anomaly 0.9 normalizes to 0.9/10 = 0.09, so
    # 0.4*0.09 + 0.3*0.60 + 0.3*0.575 = 0.3885 -> 38.85.
    assert index == pytest.approx(38.85)
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
    assert temperature_anomaly([], "EUR", _JULY) == pytest.approx(0.0)
