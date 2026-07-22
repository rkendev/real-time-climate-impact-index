"""Event source interface (UC-1, ADR-0007).

The producer depends on this Protocol, not on a concrete source, so that the
simulated generators and a real fetched feed are an adapter swap selected by
configuration, exactly as the transport and the store already are (ADR-0002,
ADR-0003). Any concrete client import stays lazy inside the adapter's run path
so test collection never triggers it.

Unlike :mod:`climate_index.interfaces.transport` and
:mod:`climate_index.interfaces.store`, which type their payloads structurally to
avoid depending on the entity models, this interface names the models directly.
That is the whole contract: a source yields *typed, already valid* domain events,
so whatever a source does internally, nothing half formed reaches the producer.
The entity models are pure domain data with no vendor or network dependency, so
naming them here costs the core nothing (INV-4, INV-6).

A tick may legitimately be short or empty. Under the real source a reading that
fails to arrive is not emitted at all rather than being substituted or retried,
so a caller must treat a thin tick as ordinary and let the confidence grade
speak for it (UC-1 no-fabrication rule, NFR-DQ2).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from climate_index.core.models import SatelliteEvent, WeatherEvent


@runtime_checkable
class EventSource(Protocol):
    """A source of one tick of typed, already validated events."""

    def fetch_tick(self) -> Sequence[WeatherEvent | SatelliteEvent]:
        """Return the events for one tick, in no guaranteed order.

        May return fewer events than the configured regions would suggest, or
        none at all, when readings could not be obtained. That gap is the
        honest signal the confidence grader reads; it is never filled in.
        """
        ...
