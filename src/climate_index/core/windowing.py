"""Event-time tumbling-window bucketing (UC-3, FR-5, ADR-0002).

The window a record belongs to is a function of its event timestamp alone, never
of arrival (wall-clock) time. Each timestamp is floored to the window size, so
the boundaries, and therefore the natural key ``(region, window_start,
window_end)``, are reproducible across replays. This is the property idempotent
aggregate writes depend on (ADR-0002, the event-time fix): replaying the same
events reforms the same buckets and the idempotent write dedupes on the key
rather than appending a duplicate.

Pure domain logic with no transport or store dependency, so it stays under
``core`` (INV-4, AT-10).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# The tumbling grid is anchored to the Unix epoch. Anchoring to a fixed instant
# (rather than, say, the start of each hour) keeps every window size, including
# sizes that do not divide an hour evenly, on one deterministic grid.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def assign_window(ts: datetime, window_minutes: int) -> tuple[datetime, datetime]:
    """Return the ``(window_start, window_end)`` bucket for ``ts``.

    ``ts`` must be a timezone-aware UTC datetime (the event models enforce this).
    The timestamp is floored to the nearest ``window_minutes`` boundary using
    integer-second arithmetic, dropping sub-second precision, so the result is
    exact and deterministic. The interval is half-open ``[start, end)``: an event
    landing exactly on a boundary belongs to the window that boundary opens, so
    every event falls in exactly one bucket.
    """
    if window_minutes <= 0:
        raise ValueError(f"window_minutes must be positive: {window_minutes}")

    size_seconds = window_minutes * 60
    delta = ts.astimezone(UTC) - _EPOCH
    elapsed_seconds = delta.days * 86400 + delta.seconds
    start_seconds = (elapsed_seconds // size_seconds) * size_seconds

    window_start = _EPOCH + timedelta(seconds=start_seconds)
    window_end = window_start + timedelta(minutes=window_minutes)
    return window_start, window_end
