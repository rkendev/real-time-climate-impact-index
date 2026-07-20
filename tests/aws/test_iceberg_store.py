"""AT-5 on the AWS aggregate-of-record: the Iceberg MERGE half (UC-4, FR-6, NFR-R1).

Offline against the moto server, no real AWS call and no spend. Replaying the
same window produces exactly one Iceberg row; a changed metric on the same
natural key updates in place; the region series reads back ordered by window start
and isolated per region, in the same shape the DuckDB adapter returns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from climate_index.core.models import Confidence
from climate_index.interfaces import AggregateStore


def _store(ctx: Any) -> IcebergAggregateStore:
    return IcebergAggregateStore(
        catalog_properties=ctx.catalog_properties,
        namespace=ctx.namespace,
        table_name=ctx.table_name,
    )


def test_store_satisfies_protocol(aws_ctx: Any) -> None:
    assert isinstance(_store(aws_ctx), AggregateStore)


def test_upsert_then_read_returns_row_with_utc_and_enum(aws_ctx: Any, make_record: Any) -> None:
    store = _store(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=75.25))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    row = series[0]
    assert row["region"] == "EUR"
    assert row["window_start"] == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert row["window_end"] == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    assert row["impact_index"] == 75.25
    assert row["confidence"] == Confidence.MEASURED


def test_replaying_same_window_does_not_duplicate(aws_ctx: Any, make_record: Any) -> None:
    # AT-5: an identical record for the same natural key yields exactly one row
    # via the Iceberg MERGE, offline under moto.
    store = _store(aws_ctx)
    record = make_record(window_hour=12, impact=75.25)
    store.upsert(record)
    store.upsert(dict(record))
    assert len(store.read_region_series("EUR")) == 1


def test_reupsert_same_key_updates_value(aws_ctx: Any, make_record: Any) -> None:
    store = _store(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=40.0))
    store.upsert(make_record(window_hour=12, impact=88.0))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    assert series[0]["impact_index"] == 88.0


def test_read_region_series_is_ordered_by_window_start(aws_ctx: Any, make_record: Any) -> None:
    store = _store(aws_ctx)
    store.upsert(make_record(window_hour=14, impact=50.0))
    store.upsert(make_record(window_hour=9, impact=20.0))
    store.upsert(make_record(window_hour=11, impact=30.0))
    starts = [row["window_start"].hour for row in store.read_region_series("EUR")]
    assert starts == [9, 11, 14]


def test_read_region_series_isolates_regions(aws_ctx: Any, make_record: Any) -> None:
    store = _store(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=75.0, region="EUR"))
    store.upsert(make_record(window_hour=12, impact=60.0, region="NAM"))
    eur = store.read_region_series("EUR")
    assert len(eur) == 1
    assert eur[0]["impact_index"] == 75.0
    assert len(store.read_region_series("NAM")) == 1


def test_read_unknown_region_is_empty(aws_ctx: Any, make_record: Any) -> None:
    store = _store(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=75.0, region="EUR"))
    assert store.read_region_series("AFR") == []
