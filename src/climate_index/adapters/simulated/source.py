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

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from climate_index.core.generators import generate_satellite_event, generate_weather_event
from climate_index.core.models import SatelliteEvent, WeatherEvent

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from climate_index.config import CityLocation


class SimulatedEventSource:
    """Generates one weather event per region and one satellite event per city."""

    def __init__(
        self,
        regions: Sequence[str],
        locations: Mapping[str, Sequence[CityLocation]],
    ) -> None:
        self._regions = tuple(regions)
        # Required, with no default. An empty mapping would emit no satellite
        # event at all, which reads as a thinned window rather than as a
        # misconfiguration, so it is refused here the same way the real adapter
        # refuses it (E-7).
        for region in self._regions:
            if not locations.get(region):
                raise ValueError(f"no configured locations for region {region!r} (E-7)")
        self._locations = {
            region: tuple(city.name for city in locations[region]) for region in self._regions
        }

    @property
    def regions(self) -> tuple[str, ...]:
        """The regions this source generates for, in order."""
        return self._regions

    def fetch_tick(self) -> list[WeatherEvent | SatelliteEvent]:
        """Return one weather event per region and one satellite event per city.

        The satellite stream is per city because E-3 carries the sampling point,
        which is the shape the real adapter has always produced: one call per
        city, one event per city. Matching it here keeps the field shapes and the
        stream composition the same under both sources, so a window computed on
        the simulated feed is structurally the window computed on the real one.

        The weather stream stays one per region. Nothing compares against it, so
        it gained no city and its composition does not move.

        Never short and never empty: a generated reading cannot fail to arrive,
        which is exactly why the confidence signal had to be arranged by hand
        while this was the only source.
        """
        events: list[WeatherEvent | SatelliteEvent] = []
        for region in self._regions:
            events.append(generate_weather_event(region))
            for city in self._locations[region]:
                events.append(generate_satellite_event(region, city))
        return events
