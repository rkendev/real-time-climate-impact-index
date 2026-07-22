"""Windowing engine tests (UC-3, FR-4, FR-5, NFR-R4).

The engine groups validated events by natural key and emits one record per
region per window with the documented metrics and grade. Single-type windows
still yield a graded-down record rather than being dropped (NFR-R4), and output
is deterministic across event order and replays.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from climate_index.core.engine import compute_records
from climate_index.core.models import Confidence, SatelliteEvent, WeatherEvent

TS = datetime(2026, 7, 19, 12, 15, tzinfo=UTC)


def _weather(
    region: str, temperature_c: float, rainfall_mm: float, ts: datetime = TS
) -> WeatherEvent:
    return WeatherEvent(
        ts=ts,
        region=region,
        temperature_c=temperature_c,
        rainfall_mm=rainfall_mm,
        wind_speed_ms=1.0,
    )


def _satellite(region: str, ts: datetime = TS) -> SatelliteEvent:
    return SatelliteEvent(
        ts=ts, region=region, cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
    )


def test_one_record_per_region_per_window_with_expected_values() -> None:
    events = [
        _weather("EUR", 20.0, 0.0),
        _weather("EUR", 24.0, 10.0),
        SatelliteEvent(
            ts=TS, region="EUR", cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
        ),
        SatelliteEvent(
            ts=TS, region="EUR", cloud_cover_pct=30.0, vegetation_index=0.2, aerosol_index=2.0
        ),
    ]
    records = compute_records(events)
    assert len(records) == 1
    record = records[0]
    assert record.region == "EUR"
    assert record.window_start == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert record.window_end == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    # TS is in July, so the anomaly is against the EUR July normal of 21.1:
    # mean 22.0 minus 21.1 = 0.9, which normalizes to 0.09 in the index.
    assert record.temperature_anomaly == pytest.approx(0.9)
    assert record.dryness_index == pytest.approx(0.60)
    assert record.pollution_index == pytest.approx(0.575)
    assert record.impact_index == pytest.approx(38.85)
    assert record.confidence is Confidence.MEASURED


def test_the_window_month_selects_the_normal() -> None:
    """Identical readings in January and July produce different anomalies (E-7).

    The engine takes the month from the window start, so this is the wiring
    check: the same two EUR readings sit 0.9 above the July normal and 18.9
    above the January one, and nothing about the events themselves changed.
    """
    january = datetime(2026, 1, 19, 12, 15, tzinfo=UTC)
    july_records = compute_records([_weather("EUR", 20.0, 0.0), _weather("EUR", 24.0, 10.0)])
    january_records = compute_records(
        [
            _weather("EUR", 20.0, 0.0, ts=january),
            _weather("EUR", 24.0, 10.0, ts=january),
        ]
    )
    assert july_records[0].temperature_anomaly == pytest.approx(22.0 - 21.1)
    assert january_records[0].temperature_anomaly == pytest.approx(22.0 - 3.1)


def test_records_are_ordered_by_region_then_window() -> None:
    later = datetime(2026, 7, 19, 13, 15, tzinfo=UTC)
    events = [
        _weather("NAM", 15.0, 5.0),
        _satellite("NAM"),
        _weather("EUR", 15.0, 5.0, ts=later),
        _satellite("EUR", ts=later),
        _weather("EUR", 15.0, 5.0),
        _satellite("EUR"),
    ]
    records = compute_records(events)
    keys = [(record.region, record.window_start) for record in records]
    assert keys == sorted(keys)
    assert [record.region for record in records] == ["EUR", "EUR", "NAM"]


def test_two_windows_for_one_region_produce_two_records() -> None:
    later = datetime(2026, 7, 19, 12, 45, tzinfo=UTC)
    events = [
        _weather("EUR", 20.0, 1.0),
        _satellite("EUR"),
        _weather("EUR", 20.0, 1.0, ts=later),
        _satellite("EUR", ts=later),
    ]
    records = compute_records(events)
    assert len(records) == 2
    assert records[0].window_start == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert records[1].window_start == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)


def test_single_type_window_is_graded_down_not_dropped() -> None:
    # Weather-only window: still a record (NFR-R4), graded INFERRED, pollution
    # imputed to zero because no satellite input exists for it.
    events = [_weather("AFR", 30.0, 0.0), _weather("AFR", 26.0, 0.0)]
    records = compute_records(events)
    assert len(records) == 1
    assert records[0].confidence is Confidence.INFERRED
    assert records[0].pollution_index == pytest.approx(0.0)


def test_sparse_window_is_ambiguous() -> None:
    records = compute_records([_weather("ASI", 25.0, 0.0)])
    assert len(records) == 1
    assert records[0].confidence is Confidence.AMBIGUOUS


def test_output_is_deterministic_across_event_order() -> None:
    events = [
        _weather("EUR", 20.0, 0.0),
        _satellite("EUR"),
        _weather("NAM", 18.0, 2.0),
        _satellite("NAM"),
    ]
    forward = compute_records(events)
    reverse = compute_records(list(reversed(events)))
    assert [r.model_dump() for r in forward] == [r.model_dump() for r in reverse]
