"""Producer contract tests (UC-1, FR-2, NFR-S2).

Injects MemoryTransport (no concrete client). Asserts the producer emits one
weather and one satellite envelope per region per tick, each keyed by its region
(NFR-S2), and each payload re-validates through its model.
"""

from __future__ import annotations

from datetime import UTC, datetime

from climate_index.adapters.memory import MemoryTransport
from climate_index.config import get_settings
from climate_index.core.models import EventEnvelope, EventType, SatelliteEvent, WeatherEvent
from climate_index.producer import run_producer


def test_run_producer_publishes_two_events_per_region_per_tick() -> None:
    transport = MemoryTransport()
    regions = ["EUR", "NAM"]
    published = run_producer(transport, regions, ticks=3)

    assert published == 2 * len(regions) * 3
    messages = list(transport.consume())
    assert len(messages) == published

    for key, value in messages:
        envelope = EventEnvelope.model_validate(value)
        assert envelope.key == key
        assert key in regions
        if envelope.event_type is EventType.WEATHER:
            WeatherEvent.model_validate(envelope.payload)
        else:
            SatelliteEvent.model_validate(envelope.payload)


def test_run_producer_defaults_to_configured_regions() -> None:
    transport = MemoryTransport()
    published = run_producer(transport, ticks=1)
    assert published == 2 * len(get_settings().region_list)


def test_each_region_gets_one_weather_and_one_satellite_per_tick() -> None:
    transport = MemoryTransport()
    run_producer(transport, ["EUR"], ticks=1)
    types = sorted(EventEnvelope.model_validate(v).event_type for _, v in transport.consume())
    assert types == [EventType.SATELLITE, EventType.WEATHER]


def test_message_key_matches_payload_region() -> None:
    transport = MemoryTransport()
    run_producer(transport, ["AFR", "ASI"], ticks=1)
    for key, value in transport.consume():
        envelope = EventEnvelope.model_validate(value)
        assert envelope.payload["region"] == key


def test_it_publishes_whatever_the_injected_source_yields() -> None:
    """The producer is a pump, not a generator: it emits the source's tick (UC-1)."""
    ts = datetime(2026, 7, 19, 12, 15, tzinfo=UTC)
    only_weather = WeatherEvent(
        ts=ts, region="EUR", temperature_c=18.0, rainfall_mm=0.0, wind_speed_ms=3.0
    )

    class OneEventSource:
        def fetch_tick(self) -> list[WeatherEvent | SatelliteEvent]:
            return [only_weather]

    transport = MemoryTransport()
    published = run_producer(transport, ["EUR"], ticks=2, source=OneEventSource())

    assert published == 2
    types = [EventEnvelope.model_validate(v).event_type for _, v in transport.consume()]
    assert types == [EventType.WEATHER, EventType.WEATHER]


def test_a_thin_tick_publishes_fewer_rather_than_failing() -> None:
    """Under the real source a missing reading is ordinary, not an error (UC-1).

    The producer must not backfill it, raise on it, or treat the short tick as a
    failure. It publishes what arrived and lets the confidence grade downstream
    speak for the gap.
    """

    class EmptySource:
        def fetch_tick(self) -> list[WeatherEvent | SatelliteEvent]:
            return []

    transport = MemoryTransport()
    published = run_producer(transport, ["EUR", "NAM"], ticks=3, source=EmptySource())

    assert published == 0
    assert list(transport.consume()) == []
