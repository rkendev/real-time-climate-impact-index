"""Kafka transport adapter for the infra path.

Re-exports KafkaTransport. The class definition imports no Kafka client at
module scope (the client import is lazy inside the run path), so importing this
package stays collection-safe.
"""

from climate_index.adapters.kafka.transport import KafkaTransport

__all__ = ["KafkaTransport"]
