"""Event producer (UC-1, FR-1, FR-2, NFR-S2).

Per tick and region, build one WeatherEvent and one SatelliteEvent, wrap each in
a region-keyed EventEnvelope, and publish through the injected Transport
Protocol. ``run_producer`` depends on the Protocol, never a concrete client, so
tests inject MemoryTransport.

The ``__main__`` entry point wires the concrete Kafka adapter for
``make run_producer``. The adapter import is lazy and lives only in the broker
branch, so importing this module pulls in no Kafka client (the earlier build's
collection-breaking import chain stays out of the import graph).
"""

from __future__ import annotations

from collections.abc import Sequence

from climate_index.config import get_settings
from climate_index.core.generators import generate_satellite_event, generate_weather_event
from climate_index.core.models import EventEnvelope
from climate_index.interfaces import Transport
from climate_index.logging_utils import StructuredLogger, get_logger


def run_producer(
    transport: Transport,
    regions: Sequence[str] | None = None,
    *,
    ticks: int = 1,
    logger: StructuredLogger | None = None,
) -> int:
    """Publish one weather and one satellite envelope per region per tick.

    Returns the number of messages published. ``regions`` defaults to the
    configured region set; the region is always the transport partition key
    (NFR-S2).
    """
    if regions is None:
        regions = get_settings().region_list
    log = logger if logger is not None else get_logger("producer")

    published = 0
    for _ in range(ticks):
        for region in regions:
            for event in (
                generate_weather_event(region),
                generate_satellite_event(region),
            ):
                envelope = EventEnvelope.wrap(event)
                transport.publish(envelope.key, envelope.model_dump(mode="json"))
                published += 1
        log.heartbeat(regions=len(regions), published=published)

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
