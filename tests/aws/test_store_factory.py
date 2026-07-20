"""Composition-root factory: DuckDB locally, the AWS fan-out on the cloud (INV-4).

The factory returns the DuckDB store for the local backend and the fan-out
(Iceberg aggregate-of-record composed with the DynamoDB serving store) for the AWS
backend, both behind the same AggregateStore interface. The AWS branch is proven
end to end under the moto server: one upsert lands in both stores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from climate_index.adapters.composite import CompositeAggregateStore
from climate_index.adapters.duckdb import DuckDBAggregateStore
from climate_index.config import Settings
from climate_index.interfaces import AggregateStore
from climate_index.store_factory import build_aggregate_store


def test_duckdb_backend_returns_duckdb_store(tmp_path: Path) -> None:
    settings = Settings(
        aggregate_backend="duckdb",
        aggregate_store_path=tmp_path / "aggregates.duckdb",
    )
    store = build_aggregate_store(settings)
    assert isinstance(store, AggregateStore)
    assert isinstance(store, DuckDBAggregateStore)


def test_aws_backend_returns_fanout_that_writes_both(aws_ctx: Any, make_record: Any) -> None:
    settings = Settings(
        aggregate_backend="aws",
        aws_region=aws_ctx.region,
        aws_endpoint_url=aws_ctx.endpoint,
        iceberg_namespace=aws_ctx.namespace,
        iceberg_table=aws_ctx.table_name,
        iceberg_catalog_properties=aws_ctx.catalog_properties,
        dynamo_table=aws_ctx.dynamo_table,
    )
    store = build_aggregate_store(settings)
    assert isinstance(store, CompositeAggregateStore)

    store.upsert(make_record(window_hour=12, impact=75.25))

    # The composite reads from the serving store (DynamoDB).
    served = store.read_region_series("EUR")
    assert len(served) == 1
    assert served[0]["impact_index"] == 75.25

    # The durable aggregate-of-record (Iceberg) received the same row.
    durable = IcebergAggregateStore(
        catalog_properties=aws_ctx.catalog_properties,
        namespace=aws_ctx.namespace,
        table_name=aws_ctx.table_name,
    )
    assert len(durable.read_region_series("EUR")) == 1
