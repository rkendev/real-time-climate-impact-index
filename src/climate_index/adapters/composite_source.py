"""Fan-out over several event sources, with failures counted and not swallowed.

Mirrors the store fan-out in :mod:`climate_index.adapters.composite`: one object
satisfying the ``EventSource`` Protocol, delegating to several.

The reason this file has more to say about failure than the store fan-out does is
specific to what the station source measures. **A swallowed exception here would
masquerade as the finding this project publishes.** If the station source raises
and the composite quietly returns the other source's events, the station stream
disappears, and downstream that is indistinguishable from a region genuinely
having no station coverage. The project's headline is precisely that one region
has no usable station coverage, so an adapter fault would forge its strongest
result.

That is the same shape as the void-criterion defect recorded in ADR-0009: a
failure mode that mimics the thing being measured, rather than one that announces
itself. So:

* one source raising never stops another from being asked;
* a raised failure is counted separately from an absent reading, because the
  no-fabrication rule makes an absent reading meaningful and a fault meaningless;
* the failure is logged with the source that produced it and re-raised nowhere,
  so a partial tick is visibly partial rather than silently short.

The counter is the part that matters. A gap that was never distinguished from a
fault is a gap nobody can interpret later.
"""

from __future__ import annotations

from collections.abc import Sequence

from climate_index.core.models import SatelliteEvent, StationObservation, WeatherEvent
from climate_index.interfaces.source import EventSource
from climate_index.logging_utils import StructuredLogger, get_logger

_Event = WeatherEvent | SatelliteEvent | StationObservation


class CompositeEventSource:
    """Asks every configured source for a tick and concatenates what arrives."""

    def __init__(
        self,
        sources: Sequence[tuple[str, EventSource]],
        *,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._sources = tuple(sources)
        self._log = logger if logger is not None else get_logger("composite_source")
        self._failures: dict[str, int] = {name: 0 for name, _ in self._sources}

    @property
    def source_failure_counts(self) -> dict[str, int]:
        """Per source, how many ticks raised rather than returning events.

        Deliberately not folded into any adapter's ``missing_count``. A missing
        reading means the provider had nothing, which is a fact about the world
        and is what the confidence and provenance grades are built to read. A
        raised failure means this process could not ask, which is a fact about
        this process and carries no information about coverage at all.
        """
        return dict(self._failures)

    def fetch_tick(self) -> Sequence[_Event]:
        events: list[_Event] = []
        for name, source in self._sources:
            try:
                events.extend(source.fetch_tick())
            except Exception as error:  # noqa: BLE001 - counted and logged, never hidden
                self._failures[name] += 1
                self._log.event(
                    "source_tick_failed",
                    source=name,
                    error=type(error).__name__,
                    note="counted as a source fault, not as an absent reading",
                )
        return events
