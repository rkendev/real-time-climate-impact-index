"""DynamoDB serving-store idempotency and read contract (NFR-R1, NFR-P3).

Offline against the moto server, no spend. This is distinct from AT-5 (the Iceberg
aggregate-of-record): here the serving store is idempotent on the same natural key
via PutItem overwrite, the region series reads back in window-start order, a float
metric round-trips through Decimal without loss of meaning, and regions are
isolated by partition. The read-only reader returns the same shape without any
write capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from climate_index.adapters.aws.dynamo_reader import DynamoReadOnlyAggregateStore
from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
from climate_index.core.models import Confidence
from climate_index.interfaces import AggregateStore


def _writer(ctx: Any) -> DynamoAggregateStore:
    return DynamoAggregateStore(
        table_name=ctx.dynamo_table,
        region=ctx.region,
        endpoint_url=ctx.endpoint,
    )


def _reader(ctx: Any) -> DynamoReadOnlyAggregateStore:
    return DynamoReadOnlyAggregateStore(
        table_name=ctx.dynamo_table,
        region=ctx.region,
        endpoint_url=ctx.endpoint,
    )


def test_writer_satisfies_protocol(aws_ctx: Any) -> None:
    assert isinstance(_writer(aws_ctx), AggregateStore)


def test_reader_has_no_write_capability(aws_ctx: Any) -> None:
    # INV-2: the read-only reader exposes read_region_series but no upsert, so it
    # is deliberately not a full AggregateStore (which requires upsert).
    reader = _reader(aws_ctx)
    assert hasattr(reader, "read_region_series")
    assert not hasattr(reader, "upsert")
    assert not isinstance(reader, AggregateStore)


def test_upsert_then_read_returns_row_with_utc_and_enum(aws_ctx: Any, make_record: Any) -> None:
    store = _writer(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=75.25))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    row = series[0]
    assert row["region"] == "EUR"
    assert row["window_start"] == datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    assert row["window_end"] == datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    assert row["impact_index"] == 75.25
    assert row["confidence"] == Confidence.MEASURED


def test_reupsert_same_key_overwrites_to_one_item(aws_ctx: Any, make_record: Any) -> None:
    # NFR-R1: a replayed key overwrites rather than inserting a second item.
    store = _writer(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=40.0))
    store.upsert(make_record(window_hour=12, impact=88.0))
    series = store.read_region_series("EUR")
    assert len(series) == 1
    assert series[0]["impact_index"] == 88.0


def test_float_metric_round_trips_through_decimal(aws_ctx: Any, make_record: Any) -> None:
    store = _writer(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=33.34))
    row = store.read_region_series("EUR")[0]
    assert isinstance(row["impact_index"], float)
    assert row["impact_index"] == 33.34
    assert row["pollution_index"] == 0.575


def test_read_region_series_is_ordered_by_window_start(aws_ctx: Any, make_record: Any) -> None:
    store = _writer(aws_ctx)
    store.upsert(make_record(window_hour=14, impact=50.0))
    store.upsert(make_record(window_hour=9, impact=20.0))
    store.upsert(make_record(window_hour=11, impact=30.0))
    starts = [row["window_start"].hour for row in store.read_region_series("EUR")]
    assert starts == [9, 11, 14]


def test_regions_are_isolated_by_partition(aws_ctx: Any, make_record: Any) -> None:
    store = _writer(aws_ctx)
    store.upsert(make_record(window_hour=12, impact=75.0, region="EUR"))
    store.upsert(make_record(window_hour=12, impact=60.0, region="NAM"))
    eur = store.read_region_series("EUR")
    assert len(eur) == 1
    assert eur[0]["impact_index"] == 75.0
    assert len(store.read_region_series("NAM")) == 1


def test_read_only_reader_sees_writes(aws_ctx: Any, make_record: Any) -> None:
    _writer(aws_ctx).upsert(make_record(window_hour=12, impact=75.25))
    series = _reader(aws_ctx).read_region_series("EUR")
    assert len(series) == 1
    assert series[0]["impact_index"] == 75.25
