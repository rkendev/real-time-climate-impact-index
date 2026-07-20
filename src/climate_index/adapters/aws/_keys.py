"""Canonical UTC key derivation shared by the AWS aggregate adapters (INV-1 free).

Idempotency on the cloud path is only as good as the key. The Iceberg identifier
fields ``(region, window_start, window_end)`` and the DynamoDB sort key
``window_start`` are both derived here, from one normalization, so a replayed
record yields byte-identical key values in both stores: the Iceberg MERGE and the
DynamoDB PutItem then overwrite rather than insert a duplicate (FR-6, NFR-R1,
AT-5). Timezone or precision drift between the two derivations would let a replay
land as a second row, so there is exactly one formatter.

This module imports no cloud SDK; it is pure ``datetime`` and safe to import from
either aggregate adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime


def canonical_window_dt(value: datetime | str) -> datetime:
    """Normalize a window boundary to a timezone-aware UTC datetime.

    Accepts a datetime (naive is assumed UTC; aware is converted to UTC) or an
    ISO-8601 string. This is the value written to an Iceberg ``timestamptz``
    identifier field, so a replay of the same instant produces an equal value and
    the MERGE matches on the natural key.
    """
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def canonical_window_key(value: datetime | str) -> str:
    """Return the fixed-width ISO-8601 UTC string form of a window boundary.

    Microsecond precision and a constant ``+00:00`` offset make the string
    fixed-width, so lexical order equals chronological order (the DynamoDB sort
    key requirement) and a replayed record yields the same key (an overwrite, not
    a second item).
    """
    return canonical_window_dt(value).isoformat(timespec="microseconds")


def to_aware_utc(value: datetime | str) -> datetime:
    """Reattach or normalize UTC to a boundary read back from a store.

    A stored ISO string parses back to a timezone-aware UTC datetime; a naive
    datetime is treated as UTC. The result matches the timezone-aware UTC shape
    the DuckDB adapter returns, so consumers see one contract across stores.
    """
    return canonical_window_dt(value)
