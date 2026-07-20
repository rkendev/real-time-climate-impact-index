"""Read-contract parity: swapping stores does not change what a consumer sees.

For the same input, the Iceberg read and the DynamoDB read return records equal to
what the DuckDB adapter returns, so any consumer is contract-compatible across
stores (the local-to-AWS move is an adapter swap, INV-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from climate_index.adapters.duckdb import DuckDBAggregateStore


def test_iceberg_and_dynamo_reads_match_duckdb(
    aws_ctx: Any, make_record: Any, tmp_path: Path
) -> None:
    record = make_record(window_hour=12, impact=75.25)

    duckdb_store = DuckDBAggregateStore(tmp_path / "aggregates.duckdb")
    iceberg_store = IcebergAggregateStore(
        catalog_properties=aws_ctx.catalog_properties,
        namespace=aws_ctx.namespace,
        table_name=aws_ctx.table_name,
    )
    dynamo_store = DynamoAggregateStore(
        table_name=aws_ctx.dynamo_table,
        region=aws_ctx.region,
        endpoint_url=aws_ctx.endpoint,
    )
    for store in (duckdb_store, iceberg_store, dynamo_store):
        store.upsert(record)

    duck_rows = duckdb_store.read_region_series("EUR")
    iceberg_rows = iceberg_store.read_region_series("EUR")
    dynamo_rows = dynamo_store.read_region_series("EUR")
    duckdb_store.close()

    assert len(duck_rows) == len(iceberg_rows) == len(dynamo_rows) == 1
    # Confidence compares equal across str and the StrEnum, and timestamps compare
    # as instants, so the reconstructed dicts are equal to the DuckDB baseline.
    assert iceberg_rows[0] == duck_rows[0]
    assert dynamo_rows[0] == duck_rows[0]
