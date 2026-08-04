"""The frozen boundary: station observations change no index value and no grade.

UC-3 and NFR-DQ2 freeze this. Station coverage feeds the provenance tier (E-11)
alone. Feeding it into the confidence grader would drop a tier on every window
without coverage for a reason unrelated to disagreement, would put uncovered
regions at the lower tier under two mechanisms at once, and would change the
meaning of grades already shipped without any claim being measured.

This is the property most likely to break silently, so it is asserted by
comparing whole records rather than by inspecting one field, and the guard is
proven red by feeding station events into a bucket in core/engine.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from climate_index.core import validation as validation_module
from climate_index.core.engine import compute_records
from climate_index.core.models import (
    Confidence,
    Construction,
    EventEnvelope,
    EventType,
    ReasonCode,
    SatelliteEvent,
    StationObservation,
    WeatherEvent,
)
from climate_index.core.validation import ValidationGate

TS = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
TS_INFERRED = datetime(2026, 8, 1, 13, 0, tzinfo=UTC)
TS_AMBIGUOUS = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)


def _weather(ts: datetime) -> WeatherEvent:
    return WeatherEvent(ts=ts, region="EUR", temperature_c=20.0, rainfall_mm=1.0, wind_speed_ms=3.0)


def _satellite(ts: datetime) -> SatelliteEvent:
    return SatelliteEvent(
        ts=ts,
        region="EUR",
        city="Amsterdam",
        cloud_cover_pct=50.0,
        vegetation_index=0.1,
        aerosol_index=1.0,
        model_pm25_ugm3=9.0,
    )


def _index_events() -> list[WeatherEvent | SatelliteEvent]:
    """Three windows, one per confidence grade.

    Covering all three matters. A window that already grades MEASURED cannot
    change when station coverage is wrongly folded into the grade, so a fixture
    built only from complete windows would let the silent break through. The
    weather-only and sparse windows are the ones that move.
    """
    return [
        # MEASURED: both streams present.
        _weather(TS),
        _satellite(TS),
        # INFERRED: weather only, at or above the sparsity threshold.
        _weather(TS_INFERRED),
        _weather(TS_INFERRED),
        # AMBIGUOUS: a single event, below the sparsity threshold.
        _weather(TS_AMBIGUOUS),
    ]


def _station(pm25: float = 14.0, ts: datetime | None = None) -> StationObservation:
    return StationObservation(
        ts=TS if ts is None else ts,
        region="EUR",
        city="Amsterdam",
        station_id="NL-1",
        pm25_ugm3=pm25,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )


def _stations_in_every_window() -> list[StationObservation]:
    return [_station(ts=TS), _station(ts=TS_INFERRED), _station(ts=TS_AMBIGUOUS)]


def test_station_events_change_no_record_field() -> None:
    without = compute_records(_index_events())
    with_stations = compute_records([*_index_events(), *_stations_in_every_window()])
    assert with_stations == without, "a station observation altered an index record"


def test_the_fixture_covers_all_three_grades() -> None:
    """Without this the guard above can pass over a fixture that cannot move."""
    grades = {record.confidence for record in compute_records(_index_events())}
    assert grades == {Confidence.MEASURED, Confidence.INFERRED, Confidence.AMBIGUOUS}


def test_station_events_alone_produce_no_record() -> None:
    """They must not bring a region-window into existence either."""
    assert compute_records([_station()]) == []


def test_a_station_observation_survives_the_gate() -> None:
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station()).model_dump(mode="json")
    assert message["event_type"] == EventType.STATION
    validated = gate.validate(message)
    assert isinstance(validated, StationObservation)
    assert gate.quarantined_count == 0


def test_a_negative_station_reading_is_kept() -> None:
    """The frozen rule retains negatives; clamping would bias the value upward."""
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station(-3.2)).model_dump(mode="json")
    validated = gate.validate(message)
    assert isinstance(validated, StationObservation)
    assert validated.pm25_ugm3 == -3.2


def test_a_malformed_station_payload_quarantines() -> None:
    """Seeded violation one: the widened gate must reject, not forward."""
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station()).model_dump(mode="json")
    del message["payload"]["station_id"]
    assert gate.validate(message) is None
    assert gate.quarantined_count == 1
    assert gate.quarantines[0].reason_code is ReasonCode.SCHEMA
    assert gate.quarantines[0].event_type == "station"


def test_a_station_reading_below_its_sample_bound_quarantines_as_range() -> None:
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station()).model_dump(mode="json")
    message["payload"]["sample_count"] = 0
    assert gate.validate(message) is None
    assert gate.quarantines[0].reason_code is ReasonCode.RANGE


def test_an_undeclared_event_type_quarantines() -> None:
    """Seeded violation two: an unknown type must not pass the widened gate."""
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station()).model_dump(mode="json")
    message["event_type"] = "teleport"
    assert gate.validate(message) is None
    assert gate.quarantined_count == 1
    assert gate.quarantines[0].reason_code is ReasonCode.SCHEMA


def test_a_declared_type_with_no_model_quarantines_rather_than_crashing() -> None:
    """Seeded violation three, which the code shape makes necessary.

    The model lookup used to be an unguarded dict access, so an EventType member
    added without a matching entry raised KeyError out of validate(). That is the
    gate dying instead of rejecting, in the component whose whole job is not to
    die on bad input. This proves the guarded lookup, by removing an entry rather
    than by inventing an enum member.
    """
    gate = ValidationGate()
    message = EventEnvelope.wrap(_station()).model_dump(mode="json")
    original = validation_module._MODEL_BY_TYPE.pop(EventType.STATION)
    try:
        assert gate.validate(message) is None
    finally:
        validation_module._MODEL_BY_TYPE[EventType.STATION] = original
    assert gate.quarantined_count == 1
    assert gate.quarantines[0].reason_code is ReasonCode.SCHEMA
