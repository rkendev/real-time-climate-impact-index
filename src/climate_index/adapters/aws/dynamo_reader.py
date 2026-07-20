"""Read-only DynamoDB serving reader for the dashboard (UC-5, INV-2, NFR-SEC3).

The dashboard serves the region series through this reader alone. It exposes only
:meth:`read_region_series`: there is no ``upsert`` here, and this module imports
no writer and no index compute path, so the dashboard holds no write capability
(INV-2, AT-6). The read-only DynamoDB permission is granted by the IAM role in
P2-T2; this prompt does not re-wire the dashboard, which stays on the DuckDB read
path until P2-T3.

The item mapping and the region query are shared through
:mod:`climate_index.adapters.aws._dynamo`, so this reader duplicates neither the
decoding nor the writer. ``boto3`` is imported lazily in the run path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from climate_index.adapters.aws._dynamo import query_region

if TYPE_CHECKING:
    from climate_index.config import Settings


class DynamoReadOnlyAggregateStore:
    """Read-only view of the DynamoDB serving store for per-region series reads."""

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
    def from_settings(cls, settings: Settings) -> DynamoReadOnlyAggregateStore:
        """Build the reader from config (INV-1); no literal table or endpoint."""
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

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the region's items in window-start order (read-only, INV-2)."""
        return query_region(self._get_table(), region)
