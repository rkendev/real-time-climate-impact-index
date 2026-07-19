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


class MemoryCommittableConsumer:
    """In-memory consumer modelling Kafka offsets and an explicit commit (ADR-0002).

    Messages carry a monotonic offset (their append index). ``commit`` advances a
    single committed offset; ``poll`` yields only messages after it. Auto-commit
    is not modelled: nothing advances the committed offset except ``commit``, so a
    crash before commit leaves the window's events uncommitted and they replay on
    the next ``poll``. This turns the NFR-R1/NFR-R2 recovery model into a test
    that needs no broker.
    """

    def __init__(self) -> None:
        self._messages: list[tuple[str, Mapping[str, Any]]] = []
        self._committed: int = -1  # last committed offset; -1 means nothing committed

    def publish(self, key: str, value: Mapping[str, Any]) -> None:
        """Append one message to the log, copying the value to isolate callers."""
        self._messages.append((key, dict(value)))

    def poll(self) -> Iterator[tuple[int, str, Mapping[str, Any]]]:
        """Yield ``(offset, key, value)`` for every message after the committed offset."""
        for offset in range(self._committed + 1, len(self._messages)):
            key, value = self._messages[offset]
            yield offset, key, value

    def commit(self, offset: int) -> None:
        """Advance the committed offset (never moves backward)."""
        if offset > self._committed:
            self._committed = offset

    @property
    def committed_offset(self) -> int:
        """The last committed offset (-1 if nothing has been committed)."""
        return self._committed
