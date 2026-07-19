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


def main() -> None:
    """Entry point for the Kafka consumer path (deferred until infra is up).

    With no broker configured this is a safe no-op that never imports the Kafka
    client. When a broker is configured, the Kafka committable consumer is
    imported lazily here (the only place it is referenced) and one pass runs
    against the DuckDB stores.
    """
    from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore

    settings = get_settings()
    log = get_logger("consumer", _log_level(settings.log_level))

    if settings.transport_bootstrap_servers is None:
        log.event("no_broker_configured", note="set CII_TRANSPORT_BOOTSTRAP_SERVERS to consume")
        return

    from climate_index.adapters.kafka import KafkaCommittableConsumer

    consumer = KafkaCommittableConsumer(settings.transport_bootstrap_servers)
    aggregate_store = DuckDBAggregateStore(settings.aggregate_store_path)
    raw_store = DuckDBRawStore(settings.raw_store_path / "raw_events.duckdb")
    try:
        run_consumer_once(consumer, aggregate_store, raw_store, settings, logger=log)
    finally:
        aggregate_store.close()
        raw_store.close()
        consumer.close()


def _log_level(name: str) -> int:
    import logging

    return getattr(logging, name.upper(), logging.INFO)


if __name__ == "__main__":
    main()
