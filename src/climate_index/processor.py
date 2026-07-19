"""Stream processor entry point (UC-3, UC-4, FR-4..FR-7).

Drains validated events from a Transport, computes one aggregate record per
region per event-time window, and persists records (idempotently) and raw events
through the store adapters. ``run_processor`` depends only on the Transport and
store Protocols, never a concrete client, so tests inject MemoryTransport and the
DuckDB stores.

The flow is a clean batch seam: consume-and-validate, then window, then write.
The live Kafka consumer loop with the commit-after-write offset rule (ADR-0002)
is Track H; it wraps this same shape, committing offsets only once a closed
window's aggregate write has succeeded. That offset and recovery logic is
deliberately not implemented here, and nothing here depends on Kafka: the
``__main__`` path runs entirely in memory (the local-first rule).
"""

from __future__ import annotations

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore
from climate_index.adapters.memory import MemoryTransport
from climate_index.config import Settings, get_settings
from climate_index.core.engine import compute_records
from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.core.validation import ValidationGate
from climate_index.interfaces import AggregateStore, RawStore, Transport
from climate_index.logging_utils import StructuredLogger, get_logger
from climate_index.producer import run_producer


def run_processor(
    transport: Transport,
    aggregate_store: AggregateStore,
    raw_store: RawStore,
    settings: Settings | None = None,
    *,
    logger: StructuredLogger | None = None,
) -> int:
    """Consume, validate, window, and persist. Returns the number of records.

    Every consumed message passes the deterministic validation gate first
    (INV-3): a quarantined message is counted and never contributes to an
    aggregate or a raw row. Validated events are appended to the raw store
    (FR-7), then windowed into one ClimateIndexRecord per region per window and
    written to the aggregate store idempotently on the natural key (FR-6).
    """
    settings = settings if settings is not None else get_settings()
    log = logger if logger is not None else get_logger("processor")

    gate = ValidationGate()
    validated: list[WeatherEvent | SatelliteEvent] = []
    consumed = 0
    for _key, value in transport.consume():
        consumed += 1
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

    log.event(
        "processor_run_complete",
        consumed=consumed,
        forwarded=gate.forwarded_count,
        quarantined=gate.quarantined_count,
        records=len(records),
    )
    return len(records)


def main() -> None:
    """Entry point for ``make run_processor`` on the in-memory path (no Kafka).

    Populates a MemoryTransport via the producer, then runs the processor against
    the DuckDB stores whose paths come from config, and logs the per-region
    series lengths read back through the store to show the write-then-read path.
    """
    settings = get_settings()
    log = get_logger("processor", _log_level(settings.log_level))

    transport = MemoryTransport()
    run_producer(transport, logger=log)

    aggregate_store = DuckDBAggregateStore(settings.aggregate_store_path)
    raw_store = DuckDBRawStore(settings.raw_store_path / "raw_events.duckdb")
    try:
        records = run_processor(transport, aggregate_store, raw_store, settings, logger=log)
        for region in settings.region_list:
            series = aggregate_store.read_region_series(region)
            log.event("region_series", region=region, rows=len(series))
    finally:
        aggregate_store.close()
        raw_store.close()

    log.event("processor_main_complete", records=records)


def _log_level(name: str) -> int:
    import logging

    return getattr(logging, name.upper(), logging.INFO)


if __name__ == "__main__":
    main()
