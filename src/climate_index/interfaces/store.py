"""Store interfaces (NFR-PT3).

The code depends on these Protocols so that the local store (DuckDB in a later
track) maps to the AWS store shape (S3 with Iceberg for the aggregate-of-record
and raw data, plus DynamoDB as the serving store) as an adapter swap (ADR-0003).

Records and events are typed structurally (mappings keyed by string) so this
interface does not depend on the Track B entity models (E-5 ClimateIndexRecord,
raw events). Concrete typing lands in later tracks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AggregateStore(Protocol):
    """Persistence for per-region-per-window aggregate rows (E-5)."""

    def upsert(self, record: Mapping[str, Any]) -> None:
        """Write one aggregate row idempotently on its natural key.

        The natural key is (region, window_start, window_end); a replay of the
        same window must not create a duplicate row (FR-6, NFR-R1).
        """
        ...

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the aggregate rows for one region, ordered by window start.

        Read-only; used by the dashboard (UC-5, INV-2).
        """
        ...


@runtime_checkable
class ReadOnlyAggregateStore(Protocol):
    """The read-only slice of the aggregate store the dashboard depends on (UC-5).

    Exposes only :meth:`read_region_series`, never a writer, so a component typed
    against this Protocol (the dashboard) holds no write capability (INV-2, AT-6).
    Both the local DuckDB reader and the DynamoDB serving reader satisfy it, so the
    read path is a config-driven adapter swap at the composition root.
    """

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the aggregate rows for one region, ordered by window start."""
        ...


@runtime_checkable
class RawStore(Protocol):
    """Append-only persistence for validated raw events (FR-7)."""

    def append(self, event: Mapping[str, Any]) -> None:
        """Append one validated raw event for audit and replay."""
        ...
