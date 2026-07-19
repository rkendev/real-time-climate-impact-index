"""In-memory adapters for tests and the local smoke path.

These carry no external dependency, so the smoke path never depends on Kafka to
go green (ADR-0002 local-first rule).
"""

from climate_index.adapters.memory.transport import MemoryCommittableConsumer, MemoryTransport

__all__ = ["MemoryCommittableConsumer", "MemoryTransport"]
