"""Simulated EventSource: the committed generators behind the source interface.

Structurally satisfies :class:`climate_index.interfaces.source.EventSource`. This
is the default source, so with nothing configured the producer, both smoke
checks, and the local quickstart behave exactly as they did before the source
became selectable (UC-1, ADR-0007).

The adapter is a thin wrapper on purpose. The generators stay in ``core``, pure
and unchanged, so the AT-1 generator test still exercises them directly with no
adapter in the way, and this file carries no sampling logic of its own that
could drift from them.
"""

from __future__ import annotations

from collections.abc import Sequence

from climate_index.core.generators import generate_satellite_event, generate_weather_event
from climate_index.core.models import SatelliteEvent, WeatherEvent


class SimulatedEventSource:
    """Generates one weather and one satellite event per region per tick."""

    def __init__(self, regions: Sequence[str]) -> None:
        self._regions = tuple(regions)

    @property
    def regions(self) -> tuple[str, ...]:
        """The regions this source generates for, in order."""
        return self._regions

    def fetch_tick(self) -> list[WeatherEvent | SatelliteEvent]:
        """Return one weather and one satellite event for each region (FR-1).

        Never short and never empty: a generated reading cannot fail to arrive,
        which is exactly why the confidence signal had to be arranged by hand
        while this was the only source.
        """
        events: list[WeatherEvent | SatelliteEvent] = []
        for region in self._regions:
            events.append(generate_weather_event(region))
            events.append(generate_satellite_event(region))
        return events
