"""Canonical-key stability: a replay cannot silently land as a second row.

A store key re-derived from a round-tripped record must equal the key of the
original record, so the Iceberg MERGE and the DynamoDB PutItem overwrite rather
than insert. This is the crux of idempotency on the cloud path (FR-6, NFR-R1).
"""

from __future__ import annotations

from typing import Any

from climate_index.adapters.aws._dynamo import from_item, to_item
from climate_index.adapters.aws._keys import canonical_window_dt, canonical_window_key, to_aware_utc


def test_dynamo_sort_key_is_stable_across_roundtrip(make_record: Any) -> None:
    record = make_record(window_hour=12, impact=75.25)
    original = to_item(record)
    roundtrip = from_item(original)
    # The sort key re-derived from the read-back record equals the original key.
    assert to_item(roundtrip)["window_start"] == original["window_start"]
    assert canonical_window_key(roundtrip["window_start"]) == canonical_window_key(
        record["window_start"]
    )


def test_iceberg_identifier_values_are_stable_across_roundtrip(make_record: Any) -> None:
    record = make_record(window_hour=12, impact=75.25)
    start = canonical_window_dt(record["window_start"])
    end = canonical_window_dt(record["window_end"])
    # Reconstructing (to_aware_utc) then re-deriving yields the same key value.
    assert canonical_window_dt(to_aware_utc(start)) == start
    assert canonical_window_dt(to_aware_utc(end)) == end


def test_both_stores_agree_on_the_window_start_key(make_record: Any) -> None:
    record = make_record(window_hour=12, impact=75.25)
    dynamo_sort_key = to_item(record)["window_start"]
    iceberg_value = canonical_window_dt(record["window_start"])
    # The two stores derive their key from the same formatter, so they never
    # disagree: the Dynamo string is the ISO form of the Iceberg timestamp value.
    assert dynamo_sort_key == iceberg_value.isoformat(timespec="microseconds")
