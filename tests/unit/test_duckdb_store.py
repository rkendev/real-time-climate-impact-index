"""AT-5 (UC-4, FR-6, NFR-R1) and FR-7: DuckDB aggregate and raw stores.

Replaying the same window does not create a duplicate aggregate row (idempotent
on the natural key), the region series reads back ordered by window start with
UTC timestamps, and validated raw events append for audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from climate_index.adapters.duckdb import DuckDBAggregateStore, DuckDBRawStore
from climate_index.core.models import ClimateIndexRecord, Confidence
from climate_index.interfaces import AggregateStore, RawStore


def _record(window_hour: int, impact: float, region: str = "EUR") -> dict[str, object]:
    record = ClimateIndexRecord(
        region=region,
        window_start=datetime(2026, 7, 19, window_hour, 0, tzinfo=UTC),
        window_end=datetime(2026, 7, 19, window_hour, 30, tzinfo=UTC),
        impact_index=impact,
        temperature_anomaly=10.0,
        dryness_index=0.6,
        pollution_index=0.575,
        confidence=Confidence.MEASURED,
    )
    return record.model_dump(mode="python")


def test_stores_satisfy_their_protocols(tmp_path: Path) -> None:
    aggregate = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    raw = DuckDBRawStore(tmp_path / "raw.duckdb")
    assert isinstance(aggregate, AggregateStore)
    assert isinstance(raw, RawStore)


def test_upsert_then_read_returns_row_with_utc_timestamps(tmp_path: Path) -> None:
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    store.upsert(_record(12, 75.25))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    row = series[0]
    assert row["region"] == "EUR"
    assert row["window_start"] == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert row["impact_index"] == 75.25
    assert row["confidence"] == "MEASURED"


def test_replaying_same_window_does_not_duplicate(tmp_path: Path) -> None:
    # AT-5: an identical record for the same natural key yields exactly one row.
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    record = _record(12, 75.25)
    store.upsert(record)
    store.upsert(dict(record))
    series = store.read_region_series("EUR")
    assert len(series) == 1


def test_reupsert_same_key_replaces_value(tmp_path: Path) -> None:
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    store.upsert(_record(12, 40.0))
    store.upsert(_record(12, 88.0))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    assert series[0]["impact_index"] == 88.0


def test_read_region_series_is_ordered_by_window_start(tmp_path: Path) -> None:
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    store.upsert(_record(14, 50.0))
    store.upsert(_record(9, 20.0))
    store.upsert(_record(11, 30.0))
    starts = [row["window_start"].hour for row in store.read_region_series("EUR")]
    assert starts == [9, 11, 14]


def test_read_region_series_filters_by_region(tmp_path: Path) -> None:
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    store.upsert(_record(12, 75.0, region="EUR"))
    store.upsert(_record(12, 60.0, region="NAM"))
    assert len(store.read_region_series("EUR")) == 1
    assert store.read_region_series("EUR")[0]["impact_index"] == 75.0


def test_read_unknown_region_is_empty(tmp_path: Path) -> None:
    store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    assert store.read_region_series("AFR") == []


def test_raw_store_appends_validated_events(tmp_path: Path) -> None:
    raw = DuckDBRawStore(tmp_path / "raw.duckdb")
    event = {
        "event_type": "weather",
        "region": "EUR",
        "ts": datetime(2026, 7, 19, 12, 15, tzinfo=UTC),
        "payload": {"region": "EUR", "temperature_c": 20.0},
    }
    raw.append(event)
    raw.append(event)
    assert raw.count() == 2
