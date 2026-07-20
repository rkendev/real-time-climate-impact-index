"""DynamoDB serving store adapter (UC-4, FR-6, NFR-R1, NFR-P3).

The read path for the dashboard on the cloud (ADR-0003): partition key ``region``,
sort key ``window_start`` as a fixed-width ISO-8601 UTC string, so a ``Query`` on
a region returns its series in chronological order and a replayed record
overwrites the same item (idempotent on the natural key, not a second item).

This writer presents the same
:class:`~climate_index.interfaces.store.AggregateStore` shape as the DuckDB
adapter. ``boto3`` is imported lazily in the run path, so importing this module
pulls in no cloud SDK. The read-only path the dashboard uses is
:mod:`climate_index.adapters.aws.dynamo_reader` (INV-2); the shared item mapping
lives in :mod:`climate_index.adapters.aws._dynamo`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from climate_index.adapters.aws._dynamo import query_region, to_item

if TYPE_CHECKING:
    from climate_index.config import Settings


class DynamoAggregateStore:
    """Idempotent DynamoDB serving store keyed on (region, window_start)."""

    def __init__(
        self,
        *,
        table_name: str,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._endpoint_url = endpoint_url
        self._table: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> DynamoAggregateStore:
        """Build the adapter from config (INV-1); no literal table or endpoint."""
        if settings.dynamo_table is None:
            raise ValueError("CII_DYNAMO_TABLE is not configured")
        return cls(
            table_name=settings.dynamo_table,
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

    def _get_table(self) -> Any:
        """Load and cache the DynamoDB table resource (lazy SDK import)."""
        if self._table is None:
            import boto3

            resource = boto3.resource(
                "dynamodb",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            )
            self._table = resource.Table(self._table_name)
        return self._table

    def upsert(self, record: Mapping[str, Any]) -> None:
        """PutItem on the natural key (idempotent overwrite, NFR-R1)."""
        self._get_table().put_item(Item=to_item(record))

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the region's items in window-start order (read-only, INV-2)."""
        return query_region(self._get_table(), region)
