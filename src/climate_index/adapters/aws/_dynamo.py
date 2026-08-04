"""Shared DynamoDB item mapping and query helpers (single source).

The serving-store writer (:mod:`climate_index.adapters.aws.dynamo_store`) and the
read-only reader (:mod:`climate_index.adapters.aws.dynamo_reader`) both encode and
decode items and query a region series. Those live here so neither the encoding
nor the reconstruction is duplicated, and so the read-only reader can share them
without importing the writer (INV-2, AT-6), mirroring the DuckDB ``_schema``
split.

Numbers are stored as ``Decimal`` because boto3 rejects Python floats, and are
converted via ``Decimal(str(value))`` never ``Decimal(value)``: a binary float
passed straight to ``Decimal`` yields a value with more than the 38 significant
digits DynamoDB allows. On read they convert back to ``float``, and the record is
rebuilt in the same shape the DuckDB adapter returns (timezone-aware UTC
datetimes, the ``Confidence`` enum), so consumers see one contract across stores.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from climate_index.adapters.aws._keys import canonical_window_key, to_aware_utc
from climate_index.core.models import Confidence, PM25DisagreementState, ProvenanceTier

# The partition key, the sort key, and the plain window_end attribute.
PARTITION_KEY = "region"
SORT_KEY = "window_start"
_METRIC_FIELDS = (
    "impact_index",
    "temperature_anomaly",
    "dryness_index",
    "pollution_index",
)


def to_item(record: Mapping[str, Any]) -> dict[str, Any]:
    """Encode an aggregate record as a DynamoDB item.

    The sort key is the canonical fixed-width UTC string of ``window_start``, so
    lexical order equals chronological order and a replayed record overwrites the
    same item (idempotent on the natural key). ``window_end`` is a deterministic
    function of ``window_start`` for fixed windows, so it is stored as a plain
    attribute, keeping ``(region, window_start)`` a consistent key.
    """
    item: dict[str, Any] = {
        PARTITION_KEY: str(record["region"]),
        SORT_KEY: canonical_window_key(record["window_start"]),
        "window_end": canonical_window_key(record["window_end"]),
        "confidence": str(record["confidence"]),
    }
    for field in _METRIC_FIELDS:
        item[field] = Decimal(str(float(record[field])))
    # Optional, and omitted rather than written as a null: an absent attribute is
    # how DynamoDB says "not recorded". Not a key attribute, so no table
    # definition changes. Decimal(str(value)) never Decimal(value).
    value = record.get("model_pm25_ugm3")
    if value is not None:
        item["model_pm25_ugm3"] = Decimal(str(float(value)))
    # E-10 and E-11. Plain attributes, never key attributes, so no table
    # definition changes: the partition key stays region and the sort key stays
    # window_start, and a key change would be a table replacement rather than a
    # migration. Written on every reconciled row because the states are required;
    # a row that was never reconciled still says NOT_COMPARED and UNCHECKED
    # rather than omitting them, which is a different claim from an absent
    # optional measurement.
    item["pm25_disagreement"] = str(record["pm25_disagreement"])
    item["provenance_tier"] = str(record["provenance_tier"])
    item["flagged_city_count"] = int(record["flagged_city_count"])
    item["covered_city_count"] = int(record["covered_city_count"])
    item["city_comparisons"] = json.dumps(
        [dict(comparison) for comparison in record.get("city_comparisons", ())],
        default=str,
        sort_keys=True,
    )
    return item


def from_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the DuckDB-shaped record dict from a DynamoDB item."""
    record: dict[str, Any] = {
        "region": str(item[PARTITION_KEY]),
        "window_start": to_aware_utc(str(item[SORT_KEY])),
        "window_end": to_aware_utc(str(item["window_end"])),
        "confidence": Confidence(str(item["confidence"])),
    }
    for field in _METRIC_FIELDS:
        record[field] = float(item[field])
    value = item.get("model_pm25_ugm3")
    record["model_pm25_ugm3"] = None if value is None else float(value)
    # The legacy mapping for this store, in one visible place. An item written
    # before these attributes existed has none, and their absence means the
    # window was never compared and its coverage was never examined, which is
    # what the two documented states say. Not a model default, so that "never
    # reconciled" and "reconciled and not comparable" stay distinguishable
    # (NFR-DQ4).
    state = item.get("pm25_disagreement")
    record["pm25_disagreement"] = (
        PM25DisagreementState.NOT_COMPARED if state is None else PM25DisagreementState(str(state))
    )
    tier = item.get("provenance_tier")
    record["provenance_tier"] = (
        ProvenanceTier.UNCHECKED if tier is None else ProvenanceTier(str(tier))
    )
    record["flagged_city_count"] = int(item.get("flagged_city_count") or 0)
    record["covered_city_count"] = int(item.get("covered_city_count") or 0)
    raw = item.get("city_comparisons")
    record["city_comparisons"] = tuple(json.loads(str(raw))) if raw else ()
    return record


def query_region(table: Any, region: str) -> list[Mapping[str, Any]]:
    """Query one region's items in sort-key (chronological) order, paginated."""
    from boto3.dynamodb.conditions import Key

    condition = Key(PARTITION_KEY).eq(region)
    response = table.query(KeyConditionExpression=condition, ScanIndexForward=True)
    items: list[Any] = list(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=condition,
            ScanIndexForward=True,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return [from_item(item) for item in items]
