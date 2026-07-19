"""AT-2 (UC-2, FR-3, INV-3): the deterministic validation and quarantine gate.

Valid and borderline-valid events are forwarded; malformed events (bad type,
out-of-range value, unparseable payload, missing field) are quarantined with the
correct reason_code, the quarantine counter increments, and nothing invalid is
ever returned for forwarding (no bad aggregate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from climate_index.core.models import (
    EventEnvelope,
    ReasonCode,
    SatelliteEvent,
    WeatherEvent,
)
from climate_index.core.validation import ValidationGate

UTC_TS = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _weather_message(**overrides: Any) -> dict[str, Any]:
    event = WeatherEvent(
        ts=UTC_TS, region="EUR", temperature_c=10.0, rainfall_mm=1.0, wind_speed_ms=1.0
    )
    message = EventEnvelope.wrap(event).model_dump(mode="json")
    message["payload"].update(overrides)
    return message


def _satellite_message(**overrides: Any) -> dict[str, Any]:
    event = SatelliteEvent(
        ts=UTC_TS, region="NAM", cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
    )
    message = EventEnvelope.wrap(event).model_dump(mode="json")
    message["payload"].update(overrides)
    return message


def test_valid_weather_event_is_forwarded() -> None:
    gate = ValidationGate()
    event = gate.validate(_weather_message())
    assert isinstance(event, WeatherEvent)
    assert gate.forwarded_count == 1
    assert gate.quarantined_count == 0
    assert gate.quarantines == []


def test_valid_satellite_event_is_forwarded() -> None:
    gate = ValidationGate()
    event = gate.validate(_satellite_message())
    assert isinstance(event, SatelliteEvent)
    assert gate.forwarded_count == 1
    assert gate.quarantined_count == 0


def test_borderline_boundary_values_are_forwarded() -> None:
    gate = ValidationGate()
    weather = gate.validate(_weather_message(rainfall_mm=0.0, wind_speed_ms=0.0))
    satellite = gate.validate(_satellite_message(cloud_cover_pct=100.0, vegetation_index=-1.0))
    assert isinstance(weather, WeatherEvent)
    assert isinstance(satellite, SatelliteEvent)
    assert gate.forwarded_count == 2
    assert gate.quarantined_count == 0


def test_bad_event_type_is_quarantined_with_schema_reason() -> None:
    gate = ValidationGate()
    message = {"event_type": "storm", "key": "EUR", "payload": {"n": 1}}
    result = gate.validate(message)
    assert result is None
    assert gate.quarantined_count == 1
    record = gate.quarantines[-1]
    assert record.reason_code is ReasonCode.SCHEMA
    assert record.event_type == "storm"
    assert record.raw == message


def test_out_of_range_value_is_quarantined_with_range_reason() -> None:
    gate = ValidationGate()
    result = gate.validate(_weather_message(rainfall_mm=-5.0))
    assert result is None
    assert gate.quarantined_count == 1
    assert gate.quarantines[-1].reason_code is ReasonCode.RANGE


def test_non_dict_payload_is_quarantined_with_parse_reason() -> None:
    gate = ValidationGate()
    message = {"event_type": "weather", "key": "EUR", "payload": "not-a-dict"}
    result = gate.validate(message)
    assert result is None
    assert gate.quarantines[-1].reason_code is ReasonCode.PARSE


def test_unparseable_value_is_quarantined_with_parse_reason() -> None:
    gate = ValidationGate()
    result = gate.validate(_weather_message(ts="not-a-timestamp"))
    assert result is None
    assert gate.quarantines[-1].reason_code is ReasonCode.PARSE


def test_missing_required_field_is_quarantined_with_schema_reason() -> None:
    gate = ValidationGate()
    message = _weather_message()
    del message["payload"]["temperature_c"]
    result = gate.validate(message)
    assert result is None
    assert gate.quarantines[-1].reason_code is ReasonCode.SCHEMA


def test_empty_message_is_quarantined() -> None:
    gate = ValidationGate()
    result = gate.validate({})
    assert result is None
    assert gate.quarantined_count == 1


def test_counters_accumulate_and_nothing_invalid_is_forwarded() -> None:
    gate = ValidationGate()
    batch = [
        _weather_message(),
        {"event_type": "storm", "key": "EUR", "payload": {"n": 1}},
        _satellite_message(),
        _weather_message(rainfall_mm=-1.0),
        _weather_message(ts="nope"),
    ]
    forwarded = [gate.validate(message) for message in batch]

    valid = [event for event in forwarded if event is not None]
    assert len(valid) == 2
    assert all(isinstance(event, WeatherEvent | SatelliteEvent) for event in valid)
    assert gate.forwarded_count == 2
    assert gate.quarantined_count == 3
    assert len(gate.quarantines) == 3
    assert {record.reason_code for record in gate.quarantines} == {
        ReasonCode.SCHEMA,
        ReasonCode.RANGE,
        ReasonCode.PARSE,
    }
