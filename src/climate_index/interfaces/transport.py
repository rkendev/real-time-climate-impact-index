"""Transport interface (NFR-PT2).

The code depends on this Protocol, not on a concrete client, so that the local
in-memory transport, local Kafka in Docker, and the same Kafka container on AWS
are adapter swaps (ADR-0002, ADR-0003). Any concrete client import stays lazy
inside the adapter's run path so the test collection never triggers it.

The message body is typed structurally (a mapping keyed by string) so this
interface does not depend on the Track B entity models (E-4 EventEnvelope).
Concrete envelope typing lands in Track B; the key is always the region code
(NFR-S2).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """A partitioned message transport keyed by region code."""

    def publish(self, key: str, value: Mapping[str, Any]) -> None:
        """Publish one message. ``key`` is the region partition key (NFR-S2)."""
        ...

    def consume(self) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """Yield ``(key, value)`` pairs in publication order."""
        ...
