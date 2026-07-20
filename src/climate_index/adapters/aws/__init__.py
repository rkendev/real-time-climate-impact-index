"""AWS store adapters (Phase 2, ADR-0003).

Concrete :class:`~climate_index.interfaces.store.AggregateStore` and
:class:`~climate_index.interfaces.store.RawStore` implementations backed by
Amazon S3 (with Apache Iceberg for the aggregate-of-record), Amazon DynamoDB (the
serving store), and plain S3 (the raw audit trail). These are I/O adapters, so
they live outside ``core`` (INV-4, AT-10); each imports its cloud client lazily
in the run path, so importing this package pulls in no cloud SDK.
"""

from __future__ import annotations

from climate_index.adapters.aws.dynamo_reader import DynamoReadOnlyAggregateStore
from climate_index.adapters.aws.dynamo_store import DynamoAggregateStore
from climate_index.adapters.aws.iceberg_store import IcebergAggregateStore
from climate_index.adapters.aws.s3_raw_store import S3RawStore

__all__ = [
    "DynamoAggregateStore",
    "DynamoReadOnlyAggregateStore",
    "IcebergAggregateStore",
    "S3RawStore",
]
