"""Store-agnostic fan-out aggregate store (UC-4, ADR-0003).

A single :class:`~climate_index.interfaces.store.AggregateStore` composed of two
injected aggregate stores: the durable aggregate-of-record and the serving store.
The processor writes one record and this fan-out persists it to both, so the
processor stays behind the existing interface with no change (INV-4).

Durability leads: ``upsert`` writes the aggregate-of-record first, then the
serving store, and surfaces any error. A failure after the durable write leaves
the dashboard one window behind until replay rather than losing the record.
Because both writes are idempotent on the natural key, a retry after a partial
failure is safe and converges to one row in each store. Reads come from the
serving store (the dashboard path).

This module imports only the store interface; it holds no cloud SDK and is placed
outside ``core`` regardless (INV-4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from climate_index.interfaces.store import AggregateStore


class CompositeAggregateStore:
    """Fan-out over a durable aggregate-of-record and a serving store."""

    def __init__(self, durable: AggregateStore, serving: AggregateStore) -> None:
        self._durable = durable
        self._serving = serving

    def upsert(self, record: Mapping[str, Any]) -> None:
        """Write the durable store first, then the serving store (durability leads).

        Any error is surfaced. Both writes are idempotent on the natural key, so
        a retry after a partial failure converges to one row in each store.
        """
        self._durable.upsert(record)
        self._serving.upsert(record)

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Delegate reads to the serving store (the dashboard path, INV-2)."""
        return self._serving.read_region_series(region)
