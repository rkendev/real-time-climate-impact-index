"""Composition root for the event source (UC-1, INV-6, ADR-0007).

Builds the source chosen by config, exactly as
:mod:`climate_index.store_factory` builds the store chosen by config. The
producer accepts an injected interface, so the wiring lives here at the
composition root rather than in the core or in the entry point.

This module is client-free at import time: it imports only the source interface
at module scope and each concrete adapter lazily inside the selected branch, so
importing it pulls in no HTTP client (the Open-Meteo adapter keeps its own client
lazy too).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from climate_index.interfaces.source import EventSource

if TYPE_CHECKING:
    from climate_index.config import Settings
    from climate_index.logging_utils import StructuredLogger


def build_event_source(
    settings: Settings,
    regions: Sequence[str] | None = None,
    *,
    logger: StructuredLogger | None = None,
) -> EventSource:
    """Return the configured event source (the generators locally, Open-Meteo for real).

    ``regions`` defaults to the configured region set. It is a parameter because
    the producer accepts an explicit region list, and the source has to generate
    or fetch for exactly the regions the producer is publishing for.
    """
    backend = settings.source_backend
    resolved = tuple(regions) if regions is not None else settings.region_list
    primary = _build_primary(backend, settings, resolved, logger=logger)

    if settings.station_source_backend == "none":
        return primary
    if settings.station_source_backend != "openaq":
        raise ValueError(f"unknown station source backend: {settings.station_source_backend!r}")

    # Two real sources now. The composite keeps one failing from costing the
    # other, and counts a raised failure separately from an absent reading: a
    # swallowed station fault would be indistinguishable downstream from a region
    # having no station coverage, which is the finding this project publishes.
    from climate_index.adapters.composite_source import CompositeEventSource
    from climate_index.adapters.openaq import OpenAQStationSource, admitted_locations, load_artifact

    # Read, never derived. The admitted set is an outcome of the frozen rules and
    # a published figure rests on it, so it comes from a committed dated artifact
    # rather than from a startup query that could move it with nothing recording
    # that it had. Re-derivation is an explicit command.
    artifact = load_artifact(settings.station_admission_version or None)
    stations = OpenAQStationSource.from_settings(
        settings, admitted_locations(artifact), logger=logger
    )
    return CompositeEventSource([("primary", primary), ("stations", stations)], logger=logger)


def _build_primary(
    backend: str,
    settings: Settings,
    resolved: Sequence[str],
    *,
    logger: StructuredLogger | None,
) -> EventSource:
    if backend == "simulated":
        from climate_index.adapters.simulated import SimulatedEventSource

        return SimulatedEventSource(resolved, settings.region_locations)
    if backend == "real":
        from climate_index.adapters.openmeteo import OpenMeteoEventSource

        return OpenMeteoEventSource.from_settings(settings, resolved, logger=logger)
    raise ValueError(f"unknown source backend: {backend!r}")
