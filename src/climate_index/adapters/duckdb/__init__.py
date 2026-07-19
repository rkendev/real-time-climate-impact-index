"""DuckDB store adapters (Track F).

Concrete :class:`~climate_index.interfaces.store.AggregateStore` and
:class:`~climate_index.interfaces.store.RawStore` implementations backed by a
local DuckDB file. These are I/O adapters, so they live outside ``core`` (INV-4,
AT-10); DuckDB is not a cloud SDK, and the core stays free of it regardless.
"""

from __future__ import annotations

from climate_index.adapters.duckdb.reader import DuckDBReadOnlyAggregateStore
from climate_index.adapters.duckdb.store import DuckDBAggregateStore, DuckDBRawStore

__all__ = ["DuckDBAggregateStore", "DuckDBRawStore", "DuckDBReadOnlyAggregateStore"]
