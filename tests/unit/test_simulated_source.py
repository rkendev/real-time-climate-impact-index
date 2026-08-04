"""Simulated event source (UC-1, FR-1, ADR-0007).

The default source satisfies the EventSource Protocol structurally and yields
one weather event per region and one satellite event per configured city per
tick. The satellite stream is per city because E-3 carries the sampling point,
which is the shape the real adapter has always produced; matching it here keeps
the stream composition the same under both sources. Every event validates
through its own model, because a source's contract is to yield typed, already
valid domain events.
"""

from __future__ import annotations

import pytest

from climate_index.adapters.simulated import SimulatedEventSource
from climate_index.config import CityLocation
from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.interfaces import EventSource

_LOCATIONS = {
    "EUR": [
        CityLocation(name="Amsterdam", latitude=52.3676, longitude=4.9041),
        CityLocation(name="Berlin", latitude=52.5200, longitude=13.4050),
    ],
    "NAM": [CityLocation(name="New York", latitude=40.7128, longitude=-74.0060)],
}


def test_it_satisfies_the_source_protocol_structurally() -> None:
    source = SimulatedEventSource(["EUR"], _LOCATIONS)
    assert isinstance(source, EventSource)


def test_one_weather_per_region_and_one_satellite_per_city() -> None:
    source = SimulatedEventSource(["EUR", "NAM"], _LOCATIONS)
    events = source.fetch_tick()

    # Two regions: two weather events, and one satellite per configured city.
    assert len(events) == 2 + 2 + 1
    for region in ("EUR", "NAM"):
        weather = [e for e in events if isinstance(e, WeatherEvent) and e.region == region]
        assert len(weather) == 1
        satellite = [e for e in events if isinstance(e, SatelliteEvent) and e.region == region]
        assert [e.city for e in satellite] == [c.name for c in _LOCATIONS[region]]


def test_every_satellite_city_belongs_to_its_region() -> None:
    """A city label that does not belong to its region would be a fabrication."""
    events = SimulatedEventSource(["EUR", "NAM"], _LOCATIONS).fetch_tick()
    for event in events:
        if isinstance(event, SatelliteEvent):
            assert event.city in {c.name for c in _LOCATIONS[event.region]}


def test_events_are_already_valid_domain_objects() -> None:
    events = SimulatedEventSource(["EUR", "NAM"], _LOCATIONS).fetch_tick()
    for event in events:
        # Re-validating a dump is the round trip the gate will later perform.
        type(event).model_validate(event.model_dump(mode="json"))
        assert event.ts.utcoffset() is not None


def test_an_empty_region_set_yields_an_empty_tick() -> None:
    assert SimulatedEventSource([], _LOCATIONS).fetch_tick() == []


def test_a_region_with_no_configured_city_is_refused() -> None:
    """Refused at construction, not emitted as a window with no satellite event.

    An empty city list would produce weather only, which the grader reads as a
    thinned window rather than as a misconfiguration. The real adapter refuses
    the same case (E-7), and the two sources refuse it the same way.
    """
    with pytest.raises(ValueError, match="no configured locations"):
        SimulatedEventSource(["AFR"], _LOCATIONS)


def test_successive_ticks_differ() -> None:
    """The generators sample, so two ticks are not the same reading twice."""
    source = SimulatedEventSource(["EUR"], _LOCATIONS)
    first = [e.temperature_c for e in source.fetch_tick() if isinstance(e, WeatherEvent)]
    second = [e.temperature_c for e in source.fetch_tick() if isinstance(e, WeatherEvent)]
    assert first != second
