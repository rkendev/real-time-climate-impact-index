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

    if backend == "simulated":
        from climate_index.adapters.simulated import SimulatedEventSource

        return SimulatedEventSource(resolved)
    if backend == "real":
        from climate_index.adapters.openmeteo import OpenMeteoEventSource

        return OpenMeteoEventSource.from_settings(settings, resolved, logger=logger)
    raise ValueError(f"unknown source backend: {backend!r}")
