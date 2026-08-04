"""S3 + Apache Iceberg aggregate-of-record adapter (UC-4, FR-6, NFR-R1, AT-5).

The durable, idempotent aggregate store on the cloud path. One
:class:`ClimateIndexRecord` is written per natural key
``(region, window_start, window_end)`` via a client-side Iceberg MERGE
(``Table.upsert`` on the table's identifier fields), so replaying a window
overwrites its row rather than appending a duplicate (AT-5). This is the cloud
half of the mapping in ADR-0003; it presents the same
:class:`~climate_index.interfaces.store.AggregateStore` shape as the DuckDB
adapter, so the local-to-AWS move is an adapter swap (INV-4).

``pyiceberg`` and ``pyarrow`` are imported lazily inside the run path, so
importing this module pulls in no cloud SDK and test collection stays offline
(mirroring the Kafka adapter). The catalog and its file IO are built entirely
from config properties (INV-1): the pyiceberg SQL (SQLite) catalog in tests and
the Glue catalog on AWS differ only in those properties, not in this code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from climate_index.adapters.aws._keys import canonical_window_dt, to_aware_utc
from climate_index.core.models import Confidence, PM25DisagreementState, ProvenanceTier

if TYPE_CHECKING:
    from climate_index.config import Settings

# Aggregate schema, in natural-key-first order. The first three fields are the
# Iceberg identifier fields the MERGE joins on; the field ids are stable and
# 1-based as the Iceberg spec requires.
_CATALOG_NAME = "climate_index"
_IDENTIFIER_FIELDS = ("region", "window_start", "window_end")
_METRIC_FIELDS = (
    "impact_index",
    "temperature_anomaly",
    "dryness_index",
    "pollution_index",
)


class IcebergAggregateStore:
    """Idempotent S3 Iceberg aggregate-of-record keyed on the natural key."""

    def __init__(
        self,
        *,
        catalog_properties: Mapping[str, str],
        namespace: str,
        table_name: str,
        catalog_name: str = _CATALOG_NAME,
    ) -> None:
        self._catalog_properties = dict(catalog_properties)
        self._namespace = namespace
        self._table_name = table_name
        self._catalog_name = catalog_name
        self._catalog: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> IcebergAggregateStore:
        """Build the adapter from config (INV-1); no literal endpoint or bucket.

        The catalog properties select the catalog (Glue on AWS, SQL in tests);
        the warehouse, region, and optional endpoint override are threaded in from
        config. The endpoint override is None in production and set only by the
        test fixture.
        """
        properties: dict[str, str] = dict(settings.iceberg_catalog_properties)
        if settings.iceberg_warehouse_bucket and "warehouse" not in properties:
            properties["warehouse"] = f"s3://{settings.iceberg_warehouse_bucket}"
        if settings.aws_region:
            properties.setdefault("s3.region", settings.aws_region)
        if settings.aws_endpoint_url:
            properties["s3.endpoint"] = settings.aws_endpoint_url
        properties.setdefault("py-io-impl", "pyiceberg.io.pyarrow.PyArrowFileIO")
        return cls(
            catalog_properties=properties,
            namespace=settings.iceberg_namespace,
            table_name=settings.iceberg_table,
        )

    def _get_catalog(self) -> Any:
        """Load and cache the pyiceberg catalog (lazy SDK import)."""
        if self._catalog is None:
            from pyiceberg.catalog import load_catalog

            self._catalog = load_catalog(self._catalog_name, **self._catalog_properties)
        return self._catalog

    @property
    def _identifier(self) -> str:
        return f"{self._namespace}.{self._table_name}"

    def _table_schema(self) -> Any:
        """The Iceberg schema, with the natural key as identifier fields."""
        from pyiceberg.schema import Schema
        from pyiceberg.types import (
            DoubleType,
            LongType,
            NestedField,
            StringType,
            TimestamptzType,
        )

        return Schema(
            NestedField(1, "region", StringType(), required=True),
            NestedField(2, "window_start", TimestamptzType(), required=True),
            NestedField(3, "window_end", TimestamptzType(), required=True),
            NestedField(4, "impact_index", DoubleType(), required=True),
            NestedField(5, "temperature_anomaly", DoubleType(), required=True),
            NestedField(6, "dryness_index", DoubleType(), required=True),
            NestedField(7, "pollution_index", DoubleType(), required=True),
            NestedField(8, "confidence", StringType(), required=True),
            # Field ids 1 to 8 are stable and must never be reused or reordered.
            # Optional, because rows written before this field existed carry no
            # value and backfilling the shipped index is out of scope.
            NestedField(9, "model_pm25_ugm3", DoubleType(), required=False),
            # E-10 and E-11 and the three fields that support them. Optional for
            # the same reason as field 9: rows written before they existed carry
            # no value, and backfilling the shipped index is out of scope. New
            # field ids only, so nothing above is reused or reordered, and the
            # identifier fields are unchanged: the natural key still decides what
            # a MERGE matches, so replay stays idempotent (AT-5).
            NestedField(10, "pm25_disagreement", StringType(), required=False),
            NestedField(11, "provenance_tier", StringType(), required=False),
            NestedField(12, "flagged_city_count", LongType(), required=False),
            NestedField(13, "covered_city_count", LongType(), required=False),
            # The per-city detail as a JSON string, matching the local store's
            # one-column choice rather than introducing a nested type that only
            # one of the three backends could express the same way.
            NestedField(14, "city_comparisons", StringType(), required=False),
            identifier_field_ids=[1, 2, 3],
        )

    def _load_or_create_table(self) -> Any:
        """Return the aggregate table, creating it on first use if absent."""
        catalog = self._get_catalog()
        if catalog.table_exists(self._identifier):
            return catalog.load_table(self._identifier)
        catalog.create_namespace_if_not_exists(self._namespace)
        return catalog.create_table(self._identifier, schema=self._table_schema())

    def upsert(self, record: Mapping[str, Any]) -> None:
        """MERGE one aggregate row on the natural key (idempotent, AT-5).

        ``Table.upsert`` joins on the table's identifier fields, so a replayed
        record overwrites its row and a changed metric updates it in place; a new
        natural key inserts. Both make the write idempotent on the natural key.
        """
        import pyarrow as pa

        table = self._load_or_create_table()
        row = {
            "region": str(record["region"]),
            "window_start": canonical_window_dt(record["window_start"]),
            "window_end": canonical_window_dt(record["window_end"]),
            "impact_index": float(record["impact_index"]),
            "temperature_anomaly": float(record["temperature_anomaly"]),
            "dryness_index": float(record["dryness_index"]),
            "pollution_index": float(record["pollution_index"]),
            "confidence": str(record["confidence"]),
            # Nullable: None stays None rather than becoming a number.
            "model_pm25_ugm3": (
                None if record.get("model_pm25_ugm3") is None else float(record["model_pm25_ugm3"])
            ),
            # E-10 and E-11. Written on every row, including an unreconciled one,
            # which states NOT_COMPARED and UNCHECKED rather than leaving the
            # column null: never reconciled and reconciled-and-not-comparable are
            # different claims and the row makes which one it is explicit.
            "pm25_disagreement": str(record["pm25_disagreement"]),
            "provenance_tier": str(record["provenance_tier"]),
            "flagged_city_count": int(record["flagged_city_count"]),
            "covered_city_count": int(record["covered_city_count"]),
            "city_comparisons": json.dumps(
                [dict(comparison) for comparison in record.get("city_comparisons", ())],
                default=str,
                sort_keys=True,
            ),
        }
        arrow_table = pa.Table.from_pylist([row], schema=table.schema().as_arrow())
        table.upsert(arrow_table)

    def read_region_series(self, region: str) -> Sequence[Mapping[str, Any]]:
        """Return the region's rows ordered by window start (read-only, INV-2).

        Reconstructs the same element shape the DuckDB adapter returns:
        timezone-aware UTC datetimes, float metrics, and the ``Confidence`` enum,
        so any consumer is contract-compatible across stores.
        """
        catalog = self._get_catalog()
        if not catalog.table_exists(self._identifier):
            return []
        table = catalog.load_table(self._identifier)
        row_filter = f"region == {region!r}"
        scanned = table.scan(row_filter=row_filter).to_arrow().to_pylist()
        rows: list[Mapping[str, Any]] = [self._reconstruct(row) for row in scanned]
        rows.sort(key=lambda row: row["window_start"])
        return rows

    @staticmethod
    def _reconstruct(row: Mapping[str, Any]) -> dict[str, Any]:
        """Rebuild the DuckDB-shaped record dict from an Iceberg arrow row."""
        record: dict[str, Any] = {
            "region": str(row["region"]),
            "window_start": to_aware_utc(row["window_start"]),
            "window_end": to_aware_utc(row["window_end"]),
            "confidence": Confidence(str(row["confidence"])),
        }
        for field in _METRIC_FIELDS:
            record[field] = float(row[field])
        value = row.get("model_pm25_ugm3")
        record["model_pm25_ugm3"] = None if value is None else float(value)
        # The legacy mapping for this store, in one visible place. A row written
        # before these fields existed reads back null, and null means the window
        # was never compared and its coverage was never examined, which is what
        # the two documented states say.
        state = row.get("pm25_disagreement")
        record["pm25_disagreement"] = (
            PM25DisagreementState.NOT_COMPARED
            if state is None
            else PM25DisagreementState(str(state))
        )
        tier = row.get("provenance_tier")
        record["provenance_tier"] = (
            ProvenanceTier.UNCHECKED if tier is None else ProvenanceTier(str(tier))
        )
        record["flagged_city_count"] = int(row.get("flagged_city_count") or 0)
        record["covered_city_count"] = int(row.get("covered_city_count") or 0)
        raw = row.get("city_comparisons")
        record["city_comparisons"] = tuple(json.loads(str(raw))) if raw else ()
        return record
