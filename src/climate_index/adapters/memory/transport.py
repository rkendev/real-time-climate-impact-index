"""In-memory Transport implementation.

Structurally satisfies climate_index.interfaces.transport.Transport. Used by
tests and the local smoke path; it holds published messages in a list and
replays them in publication order. No external client, so importing it never
triggers a Kafka import chain (the failure that blocked the earlier build).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any


class MemoryTransport:
    """A single-process, in-memory partitioned transport keyed by region."""

    def __init__(self) -> None:
        self._messages: list[tuple[str, Mapping[str, Any]]] = []

    def publish(self, key: str, value: Mapping[str, Any]) -> None:
        """Append one message, copying the value to isolate it from callers."""
        self._messages.append((key, dict(value)))

    def consume(self) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """Yield ``(key, value)`` pairs in publication order over a snapshot."""
        yield from list(self._messages)

    def __len__(self) -> int:
        """Number of messages currently held (a count, for smoke assertions)."""
        return len(self._messages)
