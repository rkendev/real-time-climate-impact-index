"""Kafka consumer loop with commit-after-write recovery (ADR-0002, UC-6).

This is the consume side of the Kafka path: it wraps the same
consume-validate-window-write shape as the batch seam in
:mod:`climate_index.processor`, but drives a
:class:`~climate_index.interfaces.transport.CommittableConsumer` and commits
offsets only once the window's aggregate write has succeeded. Auto-commit is
disabled on the consumer, so a crash before the commit leaves the window's events
uncommitted; on restart they are reprocessed, and because event-time bucketing is
deterministic (ADR-0002 windowing) and the aggregate write is idempotent on the
natural key (FR-6), the window re-forms with no duplicate and no undercount
(NFR-R1, NFR-R2).

The loop depends only on the CommittableConsumer and store Protocols, never a
concrete client, so it is exercised with an in-memory consumer that models
offsets and a crash before commit. The ``__main__`` path wires the Kafka
consumer lazily; the live poll/commit run is deferred until infra is up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from climate_index.config import Settings, get_settings
from climate_index.core.engine import compute_records
from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.core.validation import ValidationGate
from climate_index.interfaces import AggregateStore, CommittableConsumer, RawStore
from climate_index.logging_utils import StructuredLogger, get_logger
from climate_index.store_factory import build_aggregate_store, build_raw_store, close_if_supported

# The service consumer idles this long between drains (a live loop, not a busy
# spin). Short enough that a demo sees new windows promptly, long enough to avoid
# a tight poll loop when the broker is quiet.
_IDLE_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class ConsumerRun:
    """The metadata-only outcome of one consumer pass (counts and the commit)."""

    consumed: int
    forwarded: int
    quarantined: int
    records: int
    committed_offset: int | None


def run_consumer_once(
    consumer: CommittableConsumer,
    aggregate_store: AggregateStore,
    raw_store: RawStore,
    settings: Settings | None = None,
    *,
    before_commit: Callable[[], None] | None = None,
    logger: StructuredLogger | None = None,
) -> ConsumerRun:
    """Drain the consumer, window, write aggregates, then commit (ADR-0002).

    The commit runs only after every record's idempotent aggregate write has
    succeeded, so offsets never advance past an unwritten window. ``before_commit``
    is the crash-injection seam for the recovery test: if it raises, the commit
    never runs and the drained events stay uncommitted, so a re-run reprocesses
    them and the idempotent write reforms the same window (no duplicate, no
    undercount). Returns the run counts and the committed offset (``None`` if the
    poll drained nothing).
    """
    settings = settings if settings is not None else get_settings()
    log = logger if logger is not None else get_logger("consumer")

    gate = ValidationGate()
    validated: list[WeatherEvent | SatelliteEvent] = []
    consumed = 0
    max_offset: int | None = None
    for offset, _key, value in consumer.poll():
        consumed += 1
        max_offset = offset
        event = gate.validate(value)
        if event is None:
            continue
        raw_store.append(
            {
                "event_type": value["event_type"],
                "region": event.region,
                "ts": event.ts,
                "payload": value["payload"],
            }
        )
        validated.append(event)

    records = compute_records(validated, settings)
    for record in records:
        aggregate_store.upsert(record.model_dump(mode="python"))

    # Commit-after-write (ADR-0002): the aggregate writes above are durable before
    # any offset advances. A crash injected here, before the commit, is exactly the
    # window the recovery model must survive.
    if before_commit is not None:
        before_commit()

    committed: int | None = None
    if max_offset is not None:
        consumer.commit(max_offset)
        committed = max_offset

    run = ConsumerRun(
        consumed=consumed,
        forwarded=gate.forwarded_count,
        quarantined=gate.quarantined_count,
        records=len(records),
        committed_offset=committed,
    )
    log.event(
        "consumer_run_complete",
        consumed=run.consumed,
        forwarded=run.forwarded,
        quarantined=run.quarantined,
        records=run.records,
        committed_offset=run.committed_offset if run.committed_offset is not None else -1,
    )
    return run


def run_consumer_loop(
    consumer: CommittableConsumer,
    aggregate_store: AggregateStore,
    raw_store: RawStore,
    settings: Settings,
    *,
    sleep: Callable[[float], None] | None = None,
    logger: StructuredLogger | None = None,
) -> int:
    """Drain the consumer repeatedly until stopped; return the passes run.

    The container consumer role is a live service, so it drains, then idles a
    beat, then drains again, forever (each pass reuses the same consumer, stores,
    and offsets). ``settings.consumer_oneshot`` collapses this to a single drain so
    the offline broker smoke is deterministic: produce a batch, drain once, assert.
    ``sleep`` is injected so a test can drive the loop without wall-clock waits.
    """
    log = logger if logger is not None else get_logger("consumer")
    nap = sleep if sleep is not None else _default_sleep

    passes = 0
    while True:
        run_consumer_once(consumer, aggregate_store, raw_store, settings, logger=log)
        passes += 1
        if settings.consumer_oneshot:
            break
        nap(_IDLE_POLL_SECONDS)
    return passes


def main() -> None:
    """Entry point for the Kafka consumer path (``python -m climate_index.consumer``).

    With no broker configured this is a safe no-op that never imports the Kafka
    client. When a broker is configured, the Kafka committable consumer is
    imported lazily here (the only place it is referenced) and the consume loop
    runs against the stores the composition root builds from config (DuckDB
    locally, the AWS fan-out on ``CII_AGGREGATE_BACKEND=aws``). Cleanup routes
    through :func:`close_if_supported` because the AWS stores hold no connection.
    """
    settings = get_settings()
    log = get_logger("consumer", _log_level(settings.log_level))

    if settings.transport_bootstrap_servers is None:
        log.event("no_broker_configured", note="set CII_TRANSPORT_BOOTSTRAP_SERVERS to consume")
        return

    from climate_index.adapters.kafka import KafkaCommittableConsumer

    consumer = KafkaCommittableConsumer(settings.transport_bootstrap_servers)
    aggregate_store = build_aggregate_store(settings)
    raw_store = build_raw_store(settings)
    try:
        run_consumer_loop(consumer, aggregate_store, raw_store, settings, logger=log)
    finally:
        close_if_supported(aggregate_store)
        close_if_supported(raw_store)
        consumer.close()


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _log_level(name: str) -> int:
    import logging

    return getattr(logging, name.upper(), logging.INFO)


if __name__ == "__main__":
    main()
