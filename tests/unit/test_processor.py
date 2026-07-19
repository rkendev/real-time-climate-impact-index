"""Processor end-to-end and AT-2 closure (UC-3, UC-4, FR-4..FR-7, INV-3).

The processor consumes from an in-memory transport, validates, windows, and
persists through the DuckDB stores with no Kafka. A quarantined (invalid) event
never results in an aggregate row, closing the last clause of AT-2 now that the
store exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore
from climate_index.adapters.memory import MemoryTransport
from climate_index.core.models import Confidence, EventEnvelope, SatelliteEvent, WeatherEvent
from climate_index.processor import run_processor

TS = datetime(2026, 7, 19, 12, 15, tzinfo=UTC)


def _publish(transport: MemoryTransport, event: WeatherEvent | SatelliteEvent) -> None:
    envelope = EventEnvelope.wrap(event)
    transport.publish(envelope.key, envelope.model_dump(mode="json"))


def _stores(tmp_path: Path) -> tuple[DuckDBAggregateStore, DuckDBRawStore]:
    return (
        DuckDBAggregateStore(tmp_path / "aggregates.duckdb"),
        DuckDBRawStore(tmp_path / "raw.duckdb"),
    )


def test_processor_writes_one_record_per_region(tmp_path: Path) -> None:
    transport = MemoryTransport()
    for region in ("EUR", "NAM"):
        _publish(
            transport,
            WeatherEvent(
                ts=TS, region=region, temperature_c=20.0, rainfall_mm=1.0, wind_speed_ms=1.0
            ),
        )
        _publish(
            transport,
            SatelliteEvent(
                ts=TS, region=region, cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
            ),
        )

    aggregate_store, raw_store = _stores(tmp_path)
    records = run_processor(transport, aggregate_store, raw_store)

    assert records == 2
    eur = aggregate_store.read_region_series("EUR")
    assert len(eur) == 1
    assert eur[0]["confidence"] == Confidence.MEASURED.value
    assert eur[0]["window_start"] == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert len(aggregate_store.read_region_series("NAM")) == 1
    assert raw_store.count() == 4


def test_series_is_ordered_across_windows(tmp_path: Path) -> None:
    transport = MemoryTransport()
    later = datetime(2026, 7, 19, 13, 15, tzinfo=UTC)
    for ts in (later, TS):  # publish out of chronological order
        _publish(
            transport,
            WeatherEvent(
                ts=ts, region="EUR", temperature_c=20.0, rainfall_mm=1.0, wind_speed_ms=1.0
            ),
        )
        _publish(
            transport,
            SatelliteEvent(
                ts=ts, region="EUR", cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
            ),
        )

    aggregate_store, raw_store = _stores(tmp_path)
    run_processor(transport, aggregate_store, raw_store)

    starts = [row["window_start"] for row in aggregate_store.read_region_series("EUR")]
    assert starts == sorted(starts)
    assert len(starts) == 2


def test_quarantined_event_never_becomes_an_aggregate(tmp_path: Path) -> None:
    # AT-2 closure: a valid EUR pair plus a malformed message claiming AFR. The
    # malformed message is quarantined, so AFR gets no aggregate row and only the
    # two valid events reach the raw store.
    transport = MemoryTransport()
    _publish(
        transport,
        WeatherEvent(ts=TS, region="EUR", temperature_c=20.0, rainfall_mm=1.0, wind_speed_ms=1.0),
    )
    _publish(
        transport,
        SatelliteEvent(
            ts=TS, region="EUR", cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
        ),
    )
    transport.publish("AFR", {"event_type": "storm", "key": "AFR", "payload": {"region": "AFR"}})

    aggregate_store, raw_store = _stores(tmp_path)
    records = run_processor(transport, aggregate_store, raw_store)

    assert records == 1
    assert aggregate_store.read_region_series("AFR") == []
    assert len(aggregate_store.read_region_series("EUR")) == 1
    assert raw_store.count() == 2


def test_replay_through_processor_does_not_duplicate(tmp_path: Path) -> None:
    # NFR-R1: reprocessing the same events reforms the same windows, and the
    # idempotent write leaves exactly one row per region per window.
    transport = MemoryTransport()
    _publish(
        transport,
        WeatherEvent(ts=TS, region="EUR", temperature_c=20.0, rainfall_mm=1.0, wind_speed_ms=1.0),
    )
    _publish(
        transport,
        SatelliteEvent(
            ts=TS, region="EUR", cloud_cover_pct=50.0, vegetation_index=0.0, aerosol_index=1.0
        ),
    )

    aggregate_store, raw_store = _stores(tmp_path)
    run_processor(transport, aggregate_store, raw_store)
    run_processor(transport, aggregate_store, raw_store)  # replay

    assert len(aggregate_store.read_region_series("EUR")) == 1
