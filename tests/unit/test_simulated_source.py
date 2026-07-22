"""Simulated event source (UC-1, FR-1, ADR-0007).

The default source satisfies the EventSource Protocol structurally and yields
one weather and one satellite event per region per tick, which is exactly what
the producer emitted before the source became selectable. Every event validates
through its own model, because a source's contract is to yield typed, already
valid domain events.
"""

from __future__ import annotations

from climate_index.adapters.simulated import SimulatedEventSource
from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.interfaces import EventSource


def test_it_satisfies_the_source_protocol_structurally() -> None:
    source = SimulatedEventSource(["EUR"])
    assert isinstance(source, EventSource)


def test_one_weather_and_one_satellite_per_region() -> None:
    source = SimulatedEventSource(["EUR", "NAM"])
    events = source.fetch_tick()

    assert len(events) == 4
    for region in ("EUR", "NAM"):
        for kind in (WeatherEvent, SatelliteEvent):
            matching = [e for e in events if isinstance(e, kind) and e.region == region]
            assert len(matching) == 1


def test_events_are_already_valid_domain_objects() -> None:
    events = SimulatedEventSource(["EUR", "NAM", "AFR", "ASI"]).fetch_tick()
    for event in events:
        # Re-validating a dump is the round trip the gate will later perform.
        type(event).model_validate(event.model_dump(mode="json"))
        assert event.ts.utcoffset() is not None


def test_an_empty_region_set_yields_an_empty_tick() -> None:
    assert SimulatedEventSource([]).fetch_tick() == []


def test_successive_ticks_differ() -> None:
    """The generators sample, so two ticks are not the same reading twice."""
    source = SimulatedEventSource(["EUR"])
    first = [e.temperature_c for e in source.fetch_tick() if isinstance(e, WeatherEvent)]
    second = [e.temperature_c for e in source.fetch_tick() if isinstance(e, WeatherEvent)]
    assert first != second
