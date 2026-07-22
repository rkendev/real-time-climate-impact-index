#!/usr/bin/env python3
"""Bounded backfill feeder for the live demo refresh (UC-1, FR-1, FR-2).

The committed producer role stamps every event at the current instant, so one
bounded batch forms exactly one event-time window per region. The demo wants a
snapshot that reads as a moving series, so this feeder publishes the very same
envelopes over the very same Kafka transport across a span of event-time
windows. Each refresh therefore rebuilds one bounded, self-contained history
whose whole series slides forward as time passes.

It follows the configured source (``CII_SOURCE_BACKEND``), like everything else:

* simulated: the committed generators, stamped across the last N windows, with a
  deterministic minority of windows given thinner coverage so the confidence
  mechanism is visible on a feed that cannot produce a real gap;
* real: the past day of genuine hourly readings from the Open-Meteo adapter, at
  their true timestamps. No coverage is varied and nothing is thinned. Whatever
  gaps the provider actually had are what the grader sees, which is the entire
  reason the real source is worth having.

Real mode is a continuous replay by design. Each refresh republishes hours it
has already published, and because window boundaries are a truncation of event
time and the aggregate write is idempotent on ``(region, window_start,
window_end)``, a re-published hour lands on the same row rather than duplicating
it. That is precisely the property FR-6, NFR-R1, and AT-5 exist to prove, now
exercised continuously by the public demo instead of only inside a test.

It reuses the committed generators, the envelope, the window grid, and the Kafka
transport adapter. It computes no index, opens no store, and writes nothing: the
consumer role still windows and persists what lands here, unchanged, so the
compute path and the store writer stay exactly where they are (INV-4, no core
edit). The bootstrap servers arrive from config (INV-1); no endpoint literal
appears here.

Coverage varies on purpose. A deterministic minority of the backfilled windows
receives thinner input: those windows carry weather readings only, and the oldest
of them carries a single reading. Every event stays well-formed, so nothing is
quarantined; what changes is only how much evidence a window holds. The committed
confidence computation then grades those windows down on its own (NFR-DQ2,
NFR-R4), which is what makes the provenance signal visible on the dashboard. This
feeder sets no grade and never touches a stored row: it varies the input and
lets the pipeline decide.

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

# Real mode: how many past days of hourly readings each refresh republishes. One
# day at hourly resolution is 24 windows per region at the demo's 60 minute
# window, a comparable span to the simulated backfill above and one request per
# city per endpoint however wide it is.
DEFAULT_PAST_DAYS = 1


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


def degraded_window_ages(windows: int, fraction: float) -> tuple[int, ...]:
    """Which windows get thinner coverage, by age from the newest (age zero).

    Deterministic and evenly spread, so every refresh publishes the same shape and
    the demo never depends on chance. Three rules hold the result honest:

    * the newest window is never chosen, so the value the page leads with is
      always the fully covered one;
    * at least one window is chosen whenever there is more than one, so the
      confidence mechanism is visible in every snapshot;
    * at most ``windows - 1`` are chosen, and with any sensible fraction far
      fewer, so the top tier stays the clear majority of the series.

    A single-window backfill has no room for the contrast and gets none.
    """
    if windows < 2 or fraction <= 0:
        return ()
    count = min(windows - 1, max(1, int(windows * fraction)))
    step = (windows - 1) / count
    return tuple(sorted({1 + int(position * step) for position in range(count)}))


def backfill_envelopes(
    settings: Settings,
    *,
    windows: int,
    events_per_window: int,
    now: datetime,
) -> list[EventEnvelope]:
    """Build the bounded backfill, with a deterministic minority thinly covered.

    Windows are walked oldest first up to the one currently open, on the same
    epoch-anchored grid the consumer buckets by (:func:`assign_window`), so the
    published timestamps land on exactly the windows this snapshot means to show.

    Coverage per window, and what the committed grader makes of it (NFR-DQ2):

    * most windows carry both a weather and a satellite reading per region at
      every slot, which is what grades them MEASURED;
    * the windows :func:`degraded_window_ages` picks carry weather only, so one
      component is imputed and the grade falls to INFERRED;
    * the oldest of those carries a single weather reading per region, which is
      below ``sparsity_min_events`` and grades AMBIGUOUS.

    Every region appears in every window either way, so a snapshot stays complete.
    Every event is well-formed, so the validation gate quarantines none of them:
    the only thing varying is how much evidence a window holds. With
    ``events_per_window`` at one, the weather-only windows are sparse too and
    grade AMBIGUOUS rather than INFERRED; that is the grader's call on thinner
    input, not a different intent here.
    """
    if windows <= 0:
        raise ValueError(f"windows must be positive: {windows}")
    current_start, _ = assign_window(now, settings.window_minutes)
    span = timedelta(minutes=settings.window_minutes)
    degraded = degraded_window_ages(windows, settings.demo_degraded_window_fraction)
    sparse_age = max(degraded) if degraded else None

    envelopes: list[EventEnvelope] = []
    for age in range(windows - 1, -1, -1):
        window_start = current_start - span * age
        slots = window_slots(
            window_start,
            settings.window_minutes,
            events_per_window,
            not_after=now,
        )
        if age == sparse_age:
            slots = slots[:1]
        for ts in slots:
            for region in settings.region_list:
                envelopes.append(EventEnvelope.wrap(generate_weather_event(region, ts=ts)))
                if age not in degraded:
                    envelopes.append(EventEnvelope.wrap(generate_satellite_event(region, ts=ts)))
    return envelopes


def real_backfill_envelopes(
    settings: Settings,
    *,
    past_days: int,
    logger: StructuredLogger | None = None,
) -> list[EventEnvelope]:
    """Wrap the past ``past_days`` of real hourly readings as region-keyed envelopes.

    No coverage is varied and no window is thinned: the demo knob that exists to
    make the confidence signal visible on a synthetic feed has no business here,
    because a real feed produces real gaps on its own. Whatever the provider did
    not return simply is not published, and the committed grader reads that.

    The adapter is reached by concrete type rather than through the source
    factory, because the historical fetch is deliberately not part of the
    one-tick EventSource Protocol (ADR-0007).
    """
    from climate_index.adapters.openmeteo import OpenMeteoEventSource

    source = OpenMeteoEventSource.from_settings(settings, logger=logger)
    events = source.fetch_history(past_days=past_days)
    if logger is not None:
        logger.event(
            "demo_real_history_fetched",
            past_days=past_days,
            events=len(events),
            unavailable=source.missing_count,
        )
    return [EventEnvelope.wrap(event) for event in events]


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
    """Publish one bounded backfill to the configured broker, from the configured source.

    With no broker configured this exits non-zero without importing the Kafka
    client, so a misconfigured refresh fails loudly instead of publishing an empty
    snapshot over a good one. Real mode that fetches nothing at all is treated the
    same way: publishing an empty backfill would wipe a good snapshot, and the
    refresh script keeps serving the previous one instead.
    """
    settings = get_settings()
    log = get_logger("demo_feed")

    if settings.transport_bootstrap_servers is None:
        log.event("no_broker_configured", note="set CII_TRANSPORT_BOOTSTRAP_SERVERS to publish")
        return 2

    from climate_index.adapters.kafka import KafkaTransport

    if settings.source_backend == "real":
        envelopes = real_backfill_envelopes(
            settings,
            past_days=positive_int_from_env("CII_DEMO_PAST_DAYS", DEFAULT_PAST_DAYS),
            logger=log,
        )
        if not envelopes:
            log.event("no_real_readings_available", note="serving the previous snapshot")
            return 3
    else:
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
