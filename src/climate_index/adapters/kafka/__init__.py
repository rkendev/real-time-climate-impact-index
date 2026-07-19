"""Kafka transport adapter for the infra path.

Re-exports KafkaTransport (produce/consume) and KafkaCommittableConsumer (the
commit-after-write recovery consumer, ADR-0002). Neither imports a Kafka client
at module scope (the client import is lazy inside the run path), so importing
this package stays collection-safe.
"""

from climate_index.adapters.kafka.transport import KafkaCommittableConsumer, KafkaTransport

__all__ = ["KafkaCommittableConsumer", "KafkaTransport"]
