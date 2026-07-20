"""Composition root for the aggregate store (INV-4).

Builds the stores chosen by config, both sides of the store: the writer the
processor and consumer fan out to, and the read-only view the dashboard reads.
Locally both are DuckDB; on AWS the writer is the fan-out (the S3 Iceberg
aggregate-of-record composed with the DynamoDB serving store) and the reader is the
DynamoDB serving reader. The processor, consumer, and dashboard all accept an
injected interface, so wiring lives here at the composition root, not in the core
and not in the entry points.

This module is SDK-free at import time: it imports only the store interfaces at
module scope and each concrete adapter lazily inside the selected branch, so
importing it pulls in no cloud SDK (the adapters keep their own clients lazy too).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from climate_index.interfaces.store import AggregateStore, RawStore, ReadOnlyAggregateStore

if TYPE_CHECKING:
    from climate_index.config import Settings


def close_if_supported(store: object) -> None:
    """Close a store that holds a connection; a no-op for those that do not.

    The DuckDB stores and reader own a connection and expose ``close``; the AWS
    fan-out, the Iceberg and DynamoDB stores, the S3 raw store, and the DynamoDB
    reader hold only lazy clients with nothing to release, so they expose no
    ``close``. Entry points route their ``finally`` cleanup through here so the
    same teardown works whichever backend the factory built.
    """
    close = getattr(store, "close", None)
    if callable(close):
        close()


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


def build_raw_store(settings: Settings) -> RawStore:
    """Return the configured raw store (DuckDB locally, plain S3 on AWS, FR-7).

    The raw store is selected by the same backend switch as the aggregate store,
    so a single ``CII_AGGREGATE_BACKEND`` flips both the durable aggregate path and
    the audit trail together. On AWS this is the append-only S3 raw store (a
    separate target from the aggregate-of-record, no Iceberg, no MERGE, ADR-0003).
    Each adapter is imported lazily inside its branch, so importing this module
    pulls in no cloud SDK.
    """
    backend = settings.aggregate_backend
    if backend == "duckdb":
        from climate_index.adapters.duckdb import DuckDBRawStore

        return DuckDBRawStore(settings.raw_store_path / "raw_events.duckdb")
    if backend == "aws":
        from climate_index.adapters.aws.s3_raw_store import S3RawStore

        return S3RawStore.from_settings(settings)
    raise ValueError(f"unknown aggregate backend: {backend!r}")


def build_readonly_aggregate_store(settings: Settings) -> ReadOnlyAggregateStore:
    """Return the configured read-only aggregate store the dashboard reads (INV-2).

    The read path is a config-driven adapter swap the same way the writer is: the
    local DuckDB reader, or the DynamoDB serving reader on AWS. Both expose only
    :meth:`read_region_series`, so the dashboard, typed against
    :class:`ReadOnlyAggregateStore`, holds no write capability (INV-2, AT-6). Each
    concrete reader is imported lazily inside its branch, so importing this module
    still pulls in no cloud SDK (the readers keep their own clients lazy too).
    """
    backend = settings.aggregate_backend
    if backend == "duckdb":
        from climate_index.adapters.duckdb.reader import DuckDBReadOnlyAggregateStore

        return DuckDBReadOnlyAggregateStore(settings.aggregate_store_path)
    if backend == "aws":
        from climate_index.adapters.aws.dynamo_reader import DynamoReadOnlyAggregateStore

        return DynamoReadOnlyAggregateStore.from_settings(settings)
    raise ValueError(f"unknown aggregate backend: {backend!r}")
