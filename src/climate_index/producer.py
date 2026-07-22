"""Event producer (UC-1, FR-1, FR-2, NFR-S2).

Per tick, obtain typed events from the configured EventSource, wrap each in a
region-keyed EventEnvelope, and publish through the injected Transport Protocol.
``run_producer`` depends on both Protocols and on no concrete client, so tests
inject MemoryTransport and a source of their choosing.

This module performs no network access and imports no HTTP client. Which source
is in play is decided at the composition root
(:func:`climate_index.source_factory.build_event_source`), and the concrete
adapter is imported lazily there, inside the selected branch.

A tick may publish fewer messages than the region count would suggest. Under the
real source a reading that fails to arrive is not emitted at all, so a thin tick
is ordinary rather than an error, and the confidence grade computed downstream is
what speaks for it (UC-1 no-fabrication rule, NFR-DQ2). The per-tick published
count is logged so that thinning is visible in the logs rather than silent.

The ``__main__`` entry point wires the concrete Kafka adapter for
``make run_producer``. The adapter import is lazy and lives only in the broker
branch, so importing this module pulls in no Kafka client (the earlier build's
collection-breaking import chain stays out of the import graph).
"""

from __future__ import annotations

from collections.abc import Sequence

from climate_index.config import get_settings
from climate_index.core.models import EventEnvelope
from climate_index.interfaces import EventSource, Transport
from climate_index.logging_utils import StructuredLogger, get_logger
from climate_index.source_factory import build_event_source


def run_producer(
    transport: Transport,
    regions: Sequence[str] | None = None,
    *,
    ticks: int = 1,
    source: EventSource | None = None,
    logger: StructuredLogger | None = None,
) -> int:
    """Publish one tick of the configured source's events per tick, region-keyed.

    Returns the number of messages published. ``regions`` defaults to the
    configured region set; the region is always the transport partition key
    (NFR-S2). ``source`` defaults to whatever the config selects, so existing
    callers keep the simulated behaviour they had before the source became
    selectable.
    """
    settings = get_settings()
    if regions is None:
        regions = settings.region_list
    log = logger if logger is not None else get_logger("producer")
    if source is None:
        source = build_event_source(settings, regions, logger=log)

    published = 0
    for _ in range(ticks):
        tick = source.fetch_tick()
        for event in tick:
            envelope = EventEnvelope.wrap(event)
            transport.publish(envelope.key, envelope.model_dump(mode="json"))
            published += 1
        # The per-tick count makes a thin tick visible: under the real source a
        # missing reading legitimately publishes fewer than the regions imply.
        log.heartbeat(regions=len(regions), tick_events=len(tick), published=published)

    log.event("producer_run_complete", ticks=ticks, published=published)
    return published


def main() -> None:
    """Entry point for ``make run_producer`` against the Kafka adapter path.

    With no broker configured this is a safe no-op that never imports the Kafka
    client. When a broker is configured, the Kafka adapter is imported lazily
    here (the only place it is referenced) and the producer runs one batch.
    """
    settings = get_settings()
    log = get_logger("producer", _log_level(settings.log_level))

    if settings.transport_bootstrap_servers is None:
        log.event("no_broker_configured", note="set CII_TRANSPORT_BOOTSTRAP_SERVERS to publish")
        return

    from climate_index.adapters.kafka import KafkaTransport

    transport = KafkaTransport(settings.transport_bootstrap_servers)
    run_producer(transport, logger=log)


def _log_level(name: str) -> int:
    import logging

    return getattr(logging, name.upper(), logging.INFO)


if __name__ == "__main__":
    main()
