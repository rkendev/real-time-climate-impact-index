"""Portability interfaces (T-I1).

The core depends only on these Protocols, never on a concrete transport or store
client (NFR-PT1, NFR-PT2, NFR-PT3, INV-4). Concrete adapters (the in-memory one
here in Phase 1, Kafka and the S3/DynamoDB store in Phase 2) implement them.
"""

from climate_index.interfaces.store import AggregateStore, RawStore, ReadOnlyAggregateStore
from climate_index.interfaces.transport import CommittableConsumer, Transport

__all__ = [
    "AggregateStore",
    "CommittableConsumer",
    "RawStore",
    "ReadOnlyAggregateStore",
    "Transport",
]
