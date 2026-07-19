"""NFR-R1 / NFR-R2: commit-after-write recovery, proven without a broker (ADR-0002).

An in-memory CommittableConsumer models Kafka offsets. The first pass crashes
after the window's aggregate write but before the offset commit; on restart the
uncommitted events are reprocessed, and because event-time bucketing is
deterministic and the aggregate write is idempotent on the natural key, the same
window re-forms with no duplicate row (NFR-R1) and no undercount (identical
aggregate values, NFR-R2). A final pass consumes nothing, proving the offset was
committed once the write succeeded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore
from climate_index.adapters.memory import MemoryCommittableConsumer
from climate_index.consumer import run_consumer_once
from climate_index.core.models import EventEnvelope, SatelliteEvent, WeatherEvent

TS = datetime(2026, 7, 19, 12, 15, tzinfo=UTC)
WINDOW_START = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


class SimulatedCrash(RuntimeError):
    """Injected before the offset commit to model a crash mid-window."""


def _load_full_window(consumer: MemoryCommittableConsumer) -> None:
    """Publish one weather + satellite pair per region into the consumer log."""
    for region in ("EUR", "NAM"):
        for event in (
            WeatherEvent(
                ts=TS, region=region, temperature_c=22.0, rainfall_mm=2.0, wind_speed_ms=1.0
            ),
            SatelliteEvent(
                ts=TS, region=region, cloud_cover_pct=40.0, vegetation_index=0.2, aerosol_index=1.0
            ),
        ):
            envelope = EventEnvelope.wrap(event)
            consumer.publish(envelope.key, envelope.model_dump(mode="json"))


def _rows_by_key(store: DuckDBAggregateStore) -> dict[tuple[str, datetime], float]:
    rows: dict[tuple[str, datetime], float] = {}
    for region in ("EUR", "NAM"):
        for row in store.read_region_series(region):
            rows[(row["region"], row["window_start"])] = row["impact_index"]
    return rows


def test_crash_before_commit_reprocesses_without_duplicate_or_undercount(tmp_path: Path) -> None:
    consumer = MemoryCommittableConsumer()
    _load_full_window(consumer)

    aggregate_store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    raw_store = DuckDBRawStore(tmp_path / "raw_events.duckdb")
    try:
        # First pass: the aggregate write succeeds, then a crash before the commit.
        with pytest.raises(SimulatedCrash):
            run_consumer_once(
                consumer,
                aggregate_store,
                raw_store,
                before_commit=_raise_crash,
            )

        after_crash = _rows_by_key(aggregate_store)
        assert set(after_crash) == {("EUR", WINDOW_START), ("NAM", WINDOW_START)}
        # The offset was never committed, so the events remain to be reprocessed.
        assert consumer.committed_offset == -1

        # Restart: the same events replay (nothing was committed) and the
        # idempotent write reforms the same window rather than appending.
        restart = run_consumer_once(consumer, aggregate_store, raw_store)
        assert restart.records == 2
        assert restart.committed_offset == 3  # four messages, offsets 0..3

        after_restart = _rows_by_key(aggregate_store)
        assert set(after_restart) == set(after_crash)  # no duplicate rows (NFR-R1)
        assert after_restart == after_crash  # identical aggregates, no undercount (NFR-R2)

        # A further pass consumes nothing: the offset is committed past the window.
        final = run_consumer_once(consumer, aggregate_store, raw_store)
        assert final.consumed == 0
        assert final.records == 0
        assert final.committed_offset is None
        assert _rows_by_key(aggregate_store) == after_restart
    finally:
        aggregate_store.close()
        raw_store.close()


def test_clean_pass_commits_and_forms_one_row_per_region(tmp_path: Path) -> None:
    consumer = MemoryCommittableConsumer()
    _load_full_window(consumer)

    aggregate_store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    raw_store = DuckDBRawStore(tmp_path / "raw_events.duckdb")
    try:
        run = run_consumer_once(consumer, aggregate_store, raw_store)
        assert run.consumed == 4
        assert run.records == 2
        assert run.committed_offset == 3
        assert len(aggregate_store.read_region_series("EUR")) == 1
        assert len(aggregate_store.read_region_series("NAM")) == 1
    finally:
        aggregate_store.close()
        raw_store.close()


def _raise_crash() -> None:
    raise SimulatedCrash("crash injected before offset commit")
