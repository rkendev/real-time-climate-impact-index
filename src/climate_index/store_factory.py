"""Composition root for the aggregate store (INV-4).

Builds the aggregate store the processor writes to, chosen by config: the local
DuckDB store, or the AWS fan-out (the S3 Iceberg aggregate-of-record composed with
the DynamoDB serving store). The processor already accepts an injected
:class:`~climate_index.interfaces.store.AggregateStore`, so wiring lives here at
the composition root, not in the core and not in the processor.

This module is SDK-free at import time: it imports only the store interface at
module scope and each concrete adapter lazily inside the selected branch, so
importing it pulls in no cloud SDK (the adapters keep their own clients lazy too).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from climate_index.interfaces.store import AggregateStore

if TYPE_CHECKING:
    from climate_index.config import Settings


def build_aggregate_store(settings: Settings) -> AggregateStore:
    """Return the configured aggregate store (DuckDB locally, the fan-out on AWS)."""
    backend = settings.aggregate_backend
    if backend == "duckdb":
        from climate_index.adapters.duckdb import DuckDBAggregateStore

        return DuckDBAggregateStore(settings.aggregate_store_path)
    if backend == "aws":
        from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
        from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
        from climate_index.adapters.composite import CompositeAggregateStore

        durable = IcebergAggregateStore.from_settings(settings)
        serving = DynamoAggregateStore.from_settings(settings)
        return CompositeAggregateStore(durable, serving)
    raise ValueError(f"unknown aggregate backend: {backend!r}")
