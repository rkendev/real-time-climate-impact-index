#!/usr/bin/env python3
"""Bounded backfill feeder for the live demo refresh (UC-1, FR-1, FR-2).

The committed producer role stamps every event at the current instant, so one
bounded batch forms exactly one event-time window per region. The demo wants a
snapshot that reads as a moving series, so this feeder publishes the very same
envelopes over the very same Kafka transport, but stamped across the last N
event-time windows. Each refresh therefore rebuilds one bounded, self-contained
history whose whole series slides forward as time passes.

It reuses the committed generators, the envelope, the window grid, and the Kafka
transport adapter. It computes no index, opens no store, and writes nothing: the
consumer role still windows and persists what lands here, unchanged, so the
compute path and the store writer stay exactly where they are (INV-4, no core
edit). The bootstrap servers arrive from config (INV-1); no endpoint literal
appears here.

Run inside the committed image for the length of a refresh only
(``deploy/vps/refresh.sh`` mounts this directory read-only), never as a resident
service.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from climate_index.config import Settings, get_settings
from climate_index.core.generators import generate_satellite_event, generate_weather_event
from climate_index.core.models import EventEnvelope
from climate_index.core.windowing import assign_window
from climate_index.interfaces import Transport
from climate_index.logging_utils import StructuredLogger, get_logger

# Bounded defaults: twelve windows of history, two events per stream type per
# region per window. At the 30 minute default window that is six hours of series
# and 192 messages, small enough that a refresh is a short spike rather than a
# resident load. Both are overridable from the demo environment.
DEFAULT_WINDOWS = 12
DEFAULT_EVENTS_PER_WINDOW = 2


def window_slots(
    window_start: datetime,
    window_minutes: int,
    events_per_window: int,
    *,
    not_after: datetime,
) -> tuple[datetime, ...]:
    """Return the event timestamps to emit inside one window.

    The slots are spread evenly strictly inside the window, so every event falls
    in the bucket it was meant for under the half-open ``[start, end)`` rule. A
    slot never runs past ``not_after``: the newest window is still open, so its
    later slots collapse onto the current instant rather than inventing readings
    from the future.
    """
    if events_per_window <= 0:
        raise ValueError(f"events_per_window must be positive: {events_per_window}")
    step = timedelta(minutes=window_minutes) / (events_per_window + 1)
    return tuple(
        min(window_start + step * index, not_after) for index in range(1, events_per_window + 1)
    )


def backfill_envelopes(
    settings: Settings,
    *,
    windows: int,
    events_per_window: int,
    now: datetime,
) -> list[EventEnvelope]:
    """Build the bounded backfill: both stream types per region per window.

    Windows are walked oldest first up to the one currently open, on the same
    epoch-anchored grid the consumer buckets by (:func:`assign_window`), so the
    published timestamps land on exactly the windows this snapshot means to show.
    Every window carries both a weather and a satellite reading per region, which
    is what grades each row MEASURED rather than INFERRED (NFR-DQ2).
    """
    if windows <= 0:
        raise ValueError(f"windows must be positive: {windows}")
    current_start, _ = assign_window(now, settings.window_minutes)
    span = timedelta(minutes=settings.window_minutes)

    envelopes: list[EventEnvelope] = []
    for age in range(windows - 1, -1, -1):
        window_start = current_start - span * age
        slots = window_slots(
            window_start,
            settings.window_minutes,
            events_per_window,
            not_after=now,
        )
        for ts in slots:
            for region in settings.region_list:
                envelopes.append(EventEnvelope.wrap(generate_weather_event(region, ts=ts)))
                envelopes.append(EventEnvelope.wrap(generate_satellite_event(region, ts=ts)))
    return envelopes


def publish_backfill(
    transport: Transport,
    envelopes: list[EventEnvelope],
    *,
    logger: StructuredLogger | None = None,
) -> int:
    """Publish every envelope region-keyed and return how many were sent (NFR-S2)."""
    log = logger if logger is not None else get_logger("demo_feed")
    for envelope in envelopes:
        transport.publish(envelope.key, envelope.model_dump(mode="json"))
    log.event("demo_backfill_published", published=len(envelopes))
    return len(envelopes)


def positive_int_from_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive: {value}")
    return value


def main() -> int:
    """Publish one bounded backfill to the configured broker.

    With no broker configured this exits non-zero without importing the Kafka
    client, so a misconfigured refresh fails loudly instead of publishing an empty
    snapshot over a good one.
    """
    settings = get_settings()
    log = get_logger("demo_feed")

    if settings.transport_bootstrap_servers is None:
        log.event("no_broker_configured", note="set CII_TRANSPORT_BOOTSTRAP_SERVERS to publish")
        return 2

    from climate_index.adapters.kafka import KafkaTransport

    envelopes = backfill_envelopes(
        settings,
        windows=positive_int_from_env("CII_DEMO_WINDOWS", DEFAULT_WINDOWS),
        events_per_window=positive_int_from_env(
            "CII_DEMO_EVENTS_PER_WINDOW", DEFAULT_EVENTS_PER_WINDOW
        ),
        now=datetime.now(UTC),
    )
    publish_backfill(KafkaTransport(settings.transport_bootstrap_servers), envelopes, logger=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
