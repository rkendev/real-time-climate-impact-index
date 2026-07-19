"""Schema-contract tests for the entity models (NFR-T1, E-1..E-6).

Valid and boundary values are accepted; out-of-range values, naive (non-UTC)
timestamps, and unknown region codes are rejected. Covers the envelope
round-trip that the producer and the validation gate both rely on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from climate_index.core.models import (
    ClimateIndexRecord,
    Confidence,
    EventEnvelope,
    EventType,
    QuarantineRecord,
    ReasonCode,
    SatelliteEvent,
    WeatherEvent,
)

UTC_TS = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def test_weather_event_accepts_valid_values() -> None:
    event = WeatherEvent(
        ts=UTC_TS, region="EUR", temperature_c=12.5, rainfall_mm=3.0, wind_speed_ms=4.0
    )
    assert event.region == "EUR"
    assert event.ts == UTC_TS


def test_weather_event_accepts_zero_boundary_values() -> None:
    event = WeatherEvent(
        ts=UTC_TS, region="NAM", temperature_c=-40.0, rainfall_mm=0.0, wind_speed_ms=0.0
    )
    assert event.rainfall_mm == 0.0
    assert event.wind_speed_ms == 0.0


@pytest.mark.parametrize("field", ["rainfall_mm", "wind_speed_ms"])
def test_weather_event_rejects_negative_nonneg_fields(field: str) -> None:
    kwargs = {
        "ts": UTC_TS,
        "region": "EUR",
        "temperature_c": 10.0,
        "rainfall_mm": 1.0,
        "wind_speed_ms": 1.0,
    }
    kwargs[field] = -1.0
    with pytest.raises(ValidationError):
        WeatherEvent(**kwargs)  # type: ignore[arg-type]


def test_satellite_event_accepts_boundary_values() -> None:
    low = SatelliteEvent(
        ts=UTC_TS, region="AFR", cloud_cover_pct=0.0, vegetation_index=-1.0, aerosol_index=0.0
    )
    high = SatelliteEvent(
        ts=UTC_TS, region="AFR", cloud_cover_pct=100.0, vegetation_index=1.0, aerosol_index=9.9
    )
    assert low.cloud_cover_pct == 0.0
    assert high.vegetation_index == 1.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cloud_cover_pct", 101.0),
        ("cloud_cover_pct", -0.1),
        ("vegetation_index", 1.5),
        ("vegetation_index", -1.5),
    ],
)
def test_satellite_event_rejects_out_of_range(field: str, value: float) -> None:
    kwargs = {
        "ts": UTC_TS,
        "region": "ASI",
        "cloud_cover_pct": 50.0,
        "vegetation_index": 0.0,
        "aerosol_index": 1.0,
    }
    kwargs[field] = value
    with pytest.raises(ValidationError):
        SatelliteEvent(**kwargs)  # type: ignore[arg-type]


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeatherEvent(
            ts=datetime(2026, 7, 19, 12, 0),
            region="EUR",
            temperature_c=10.0,
            rainfall_mm=1.0,
            wind_speed_ms=1.0,
        )


def test_non_utc_offset_timestamp_is_rejected() -> None:
    plus_five = timezone(timedelta(hours=5))
    with pytest.raises(ValidationError):
        WeatherEvent(
            ts=datetime(2026, 7, 19, 12, 0, tzinfo=plus_five),
            region="EUR",
            temperature_c=10.0,
            rainfall_mm=1.0,
            wind_speed_ms=1.0,
        )


def test_unknown_region_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeatherEvent(
            ts=UTC_TS, region="ZZZ", temperature_c=10.0, rainfall_mm=1.0, wind_speed_ms=1.0
        )


def test_envelope_wrap_and_json_round_trip() -> None:
    event = WeatherEvent(
        ts=UTC_TS, region="EUR", temperature_c=12.5, rainfall_mm=3.0, wind_speed_ms=4.0
    )
    envelope = EventEnvelope.wrap(event)
    assert envelope.event_type is EventType.WEATHER
    assert envelope.key == "EUR"

    dumped = envelope.model_dump(mode="json")
    reparsed = EventEnvelope.model_validate(dumped)
    assert reparsed.event_type is EventType.WEATHER
    assert WeatherEvent.model_validate(reparsed.payload) == event


def test_satellite_envelope_reports_satellite_type() -> None:
    event = SatelliteEvent(
        ts=UTC_TS, region="NAM", cloud_cover_pct=10.0, vegetation_index=0.2, aerosol_index=1.0
    )
    envelope = EventEnvelope.wrap(event)
    assert envelope.event_type is EventType.SATELLITE
    assert envelope.key == "NAM"


def test_climate_index_record_accepts_valid_row() -> None:
    record = ClimateIndexRecord(
        region="EUR",
        window_start=UTC_TS,
        window_end=UTC_TS + timedelta(minutes=30),
        impact_index=42.0,
        temperature_anomaly=1.5,
        dryness_index=0.3,
        pollution_index=0.2,
        confidence=Confidence.MEASURED,
    )
    assert record.confidence is Confidence.MEASURED


@pytest.mark.parametrize("value", [-0.1, 100.1])
def test_climate_index_record_rejects_out_of_range_index(value: float) -> None:
    with pytest.raises(ValidationError):
        ClimateIndexRecord(
            region="EUR",
            window_start=UTC_TS,
            window_end=UTC_TS + timedelta(minutes=30),
            impact_index=value,
            temperature_anomaly=0.0,
            dryness_index=0.0,
            pollution_index=0.0,
            confidence=Confidence.INFERRED,
        )


def test_quarantine_record_accepts_valid_row() -> None:
    record = QuarantineRecord(
        ts_received=UTC_TS,
        event_type="weather",
        reason_code=ReasonCode.RANGE,
        raw={"region": "EUR"},
    )
    assert record.reason_code is ReasonCode.RANGE
    assert record.raw == {"region": "EUR"}
