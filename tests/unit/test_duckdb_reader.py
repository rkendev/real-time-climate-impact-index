"""Read-only aggregate reader (UC-5, INV-2, NFR-SEC3).

The dashboard serves the store through DuckDBReadOnlyAggregateStore. This asserts
it reads back what the writer stored, and that its connection holds no write
capability: a write attempt on the read-only connection raises.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBReadOnlyAggregateStore
from climate_index.core.models import ClimateIndexRecord, Confidence

TS_START = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
TS_END = datetime(2026, 7, 19, 12, 30, tzinfo=UTC)


def _seed(db_path: Path) -> None:
    store = DuckDBAggregateStore(db_path)
    record = ClimateIndexRecord(
        region="EUR",
        window_start=TS_START,
        window_end=TS_END,
        impact_index=42.5,
        temperature_anomaly=1.0,
        dryness_index=0.5,
        pollution_index=0.5,
        confidence=Confidence.MEASURED,
    )
    store.upsert(record.model_dump(mode="python"))
    store.close()


def test_reader_reads_back_seeded_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "aggregates.duckdb"
    _seed(db_path)

    reader = DuckDBReadOnlyAggregateStore(db_path)
    try:
        rows = reader.read_region_series("EUR")
    finally:
        reader.close()

    assert len(rows) == 1
    assert rows[0]["region"] == "EUR"
    assert rows[0]["impact_index"] == 42.5
    assert rows[0]["window_start"] == TS_START
    assert rows[0]["window_start"].tzinfo is UTC
    assert rows[0]["confidence"] == Confidence.MEASURED.value


def test_reader_has_no_write_methods() -> None:
    # No write capability is exposed on the read-only serving class (INV-2).
    assert not hasattr(DuckDBReadOnlyAggregateStore, "upsert")
    assert not hasattr(DuckDBReadOnlyAggregateStore, "append")


def test_reader_connection_rejects_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "aggregates.duckdb"
    _seed(db_path)

    reader = DuckDBReadOnlyAggregateStore(db_path)
    try:
        with pytest.raises(duckdb.Error):
            reader._con.execute(
                "INSERT INTO climate_index VALUES ('EUR', ?, ?, 1.0, 0.0, 0.0, 0.0, 'MEASURED')",
                [TS_START.replace(tzinfo=None), TS_END.replace(tzinfo=None)],
            )
    finally:
        reader.close()
