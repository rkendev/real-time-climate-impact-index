"""The demo publish is atomic and the dashboard read path is never disturbed.

The live demo has one always-on reader (the dashboard, opening the served DuckDB
read-only per render) and one periodic writer (the refresh, rebuilding a snapshot
in a staging directory). These tests pin the contract that lets them share a file:

* the writer only ever holds the staging database, so the DuckDB single-writer
  lock is never taken on the served path;
* the publish is a rename, so a reader sees the whole previous snapshot or the
  whole new one, never a partial file, even under continuous reads;
* a reader that already has the file open keeps reading it safely across the
  rename, and the next reader sees the new snapshot;
* a snapshot that is incomplete, duplicated, or left with a write-ahead log is
  refused, and the previously served file is untouched.

Reads go through :func:`build_readonly_aggregate_store`, the same factory the
dashboard uses, so what is proven here is the path that is actually served.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from climate_index.adapters.duckdb import DuckDBAggregateStore
from climate_index.config import Settings
from climate_index.core.models import ClimateIndexRecord, Confidence
from climate_index.store_factory import build_readonly_aggregate_store, close_if_supported
from publish_snapshot import SnapshotError, publish_snapshot, verify_snapshot, write_ahead_log

REGIONS = ("EUR", "NAM", "AFR", "ASI")
WINDOWS = 12
WINDOW_MINUTES = 30
PUBLISH_CYCLES = 8


def _settings(served: Path) -> Settings:
    return Settings(
        regions=",".join(REGIONS),
        aggregate_backend="duckdb",
        aggregate_store_path=served,
        window_minutes=WINDOW_MINUTES,
    )


def _write_snapshot(
    db_path: Path,
    *,
    base_impact: float = 10.0,
    first_start: datetime | None = None,
    regions: tuple[str, ...] = REGIONS,
) -> None:
    """Write a complete snapshot: every region, WINDOWS windows, closed cleanly."""
    start = first_start if first_start is not None else datetime(2026, 7, 21, 6, 0, tzinfo=UTC)
    span = timedelta(minutes=WINDOW_MINUTES)
    store = DuckDBAggregateStore(db_path)
    try:
        for region in regions:
            for index in range(WINDOWS):
                window_start = start + span * index
                record = ClimateIndexRecord(
                    region=region,
                    window_start=window_start,
                    window_end=window_start + span,
                    impact_index=base_impact + index,
                    temperature_anomaly=1.0,
                    dryness_index=0.5,
                    pollution_index=0.5,
                    confidence=Confidence.MEASURED,
                )
                store.upsert(record.model_dump(mode="python"))
    finally:
        store.close()


def _read_series(settings: Settings, region: str = "EUR") -> list[float]:
    store = build_readonly_aggregate_store(settings)
    try:
        return [float(row["impact_index"]) for row in store.read_region_series(region)]
    finally:
        close_if_supported(store)


def test_reader_never_sees_a_partial_snapshot_while_refreshes_publish(tmp_path: Path) -> None:
    served = tmp_path / "served" / "aggregates.duckdb"
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    served.parent.mkdir()
    settings = _settings(served)

    _write_snapshot(served, base_impact=0.0)

    failures: list[str] = []
    reads = 0
    stop = threading.Event()

    def read_continuously() -> None:
        nonlocal reads
        while not stop.is_set():
            try:
                series = _read_series(settings)
            except Exception as exc:  # noqa: BLE001 - any failure is a finding
                failures.append(f"read raised: {exc!r}")
                return
            if len(series) != WINDOWS:
                failures.append(f"partial series of {len(series)} rows")
                return
            reads += 1

    reader = threading.Thread(target=read_continuously, name="dashboard-reader")
    reader.start()
    try:
        for cycle in range(PUBLISH_CYCLES):
            staging = staging_dir / "aggregates.duckdb"
            staging.unlink(missing_ok=True)
            _write_snapshot(staging, base_impact=10.0 * (cycle + 1))
            publish_snapshot(staging, served, settings)
    finally:
        stop.set()
        reader.join(timeout=30)

    assert not reader.is_alive(), "the reader thread did not finish"
    assert not failures, f"the dashboard read path was disturbed: {failures}"
    assert reads > 0, "the reader never completed a read, so nothing was proven"
    # The last publish is what is being served, and nothing was left half written.
    assert _read_series(settings)[0] == 10.0 * PUBLISH_CYCLES
    assert not write_ahead_log(served).exists()


def test_a_writer_holding_the_staging_database_never_blocks_the_reader(tmp_path: Path) -> None:
    served = tmp_path / "aggregates.duckdb"
    staging = tmp_path / "staging" / "aggregates.duckdb"
    settings = _settings(served)
    _write_snapshot(served)

    # The refresh's writer holds the DuckDB write lock, on the staging file only.
    writer = DuckDBAggregateStore(staging)
    try:
        assert staging.exists()
        # The dashboard opens the served file read-only at the same moment.
        assert len(_read_series(settings)) == WINDOWS
    finally:
        writer.close()


def test_an_open_reader_survives_the_rename_and_the_next_reader_sees_the_new_snapshot(
    tmp_path: Path,
) -> None:
    served = tmp_path / "aggregates.duckdb"
    staging = tmp_path / "staging" / "aggregates.duckdb"
    settings = _settings(served)
    _write_snapshot(served, base_impact=1.0)

    opened_before = build_readonly_aggregate_store(settings)
    try:
        _write_snapshot(staging, base_impact=50.0)
        publish_snapshot(staging, served, settings)

        # The handle opened before the rename still reads its own snapshot cleanly.
        before = [float(row["impact_index"]) for row in opened_before.read_region_series("EUR")]
        assert before[0] == 1.0
    finally:
        close_if_supported(opened_before)

    assert _read_series(settings)[0] == 50.0
    assert not write_ahead_log(served).exists()
    assert not staging.exists(), "the staging file was renamed, not copied"


def test_publish_refuses_a_snapshot_missing_a_region_and_leaves_the_served_file(
    tmp_path: Path,
) -> None:
    served = tmp_path / "aggregates.duckdb"
    staging = tmp_path / "staging" / "aggregates.duckdb"
    settings = _settings(served)
    _write_snapshot(served, base_impact=1.0)
    before = served.read_bytes()

    _write_snapshot(staging, base_impact=80.0, regions=("EUR", "NAM"))
    with pytest.raises(SnapshotError, match="no rows for region"):
        publish_snapshot(staging, served, settings)

    assert served.read_bytes() == before
    assert _read_series(settings)[0] == 1.0


def test_publish_refuses_a_snapshot_with_duplicate_natural_keys(tmp_path: Path) -> None:
    served = tmp_path / "aggregates.duckdb"
    staging = tmp_path / "staging" / "aggregates.duckdb"
    settings = _settings(served)
    _write_snapshot(served)
    staging.parent.mkdir(parents=True, exist_ok=True)

    # A snapshot built without the natural-key constraint the committed store
    # carries: two rows for one (region, window_start, window_end).
    con = duckdb.connect(str(staging))
    con.execute(
        """
        CREATE TABLE climate_index (
            region VARCHAR, window_start TIMESTAMP, window_end TIMESTAMP,
            impact_index DOUBLE, temperature_anomaly DOUBLE, dryness_index DOUBLE,
            pollution_index DOUBLE, confidence VARCHAR
        )
        """
    )
    for region in REGIONS:
        for impact in (10.0, 20.0):
            con.execute(
                "INSERT INTO climate_index VALUES (?, ?, ?, ?, 1.0, 0.5, 0.5, 'MEASURED')",
                [region, datetime(2026, 7, 21, 6, 0), datetime(2026, 7, 21, 6, 30), impact],
            )
    con.close()

    with pytest.raises(SnapshotError, match="duplicate natural keys"):
        publish_snapshot(staging, served, settings)
    assert staging.exists(), "a refused snapshot is left in staging, not published"


def test_verify_refuses_a_snapshot_left_with_a_write_ahead_log(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "aggregates.duckdb"
    settings = _settings(tmp_path / "aggregates.duckdb")
    _write_snapshot(staging)
    write_ahead_log(staging).write_bytes(b"")

    with pytest.raises(SnapshotError, match="write-ahead log"):
        verify_snapshot(staging, settings)


def test_verify_refuses_a_missing_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "aggregates.duckdb")
    with pytest.raises(SnapshotError, match="missing"):
        verify_snapshot(tmp_path / "staging" / "aggregates.duckdb", settings)
