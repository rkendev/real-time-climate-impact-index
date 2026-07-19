"""Kafka Transport adapter (ADR-0002, ADR-0003, NFR-S2).

Structurally satisfies climate_index.interfaces.transport.Transport. The Kafka
client import is lazy and lives inside the run path (``publish``/``consume``)
only, so importing this module or its package pulls in no client. That keeps
test collection free of the Kafka import chain; the live publish/consume test is
deferred until infra is up.

The bootstrap servers arrive from config (populated from the environment,
INV-1); no endpoint literal appears here. The topic name is a plain identifier,
not an endpoint or secret.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

_DEFAULT_TOPIC = "climate_events"
_CONSUME_POLL_TIMEOUT_S = 1.0


class KafkaTransport:
    """A region-partitioned Kafka transport keyed by region code (NFR-S2)."""

    def __init__(self, bootstrap_servers: str, topic: str = _DEFAULT_TOPIC) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer: Any | None = None

    @staticmethod
    def _client() -> Any:
        """Import the Kafka client lazily (the single import site in this module)."""
        import confluent_kafka  # type: ignore[import-not-found]

        return confluent_kafka

    def _get_producer(self) -> Any:
        """Lazily construct the Kafka producer on first publish."""
        if self._producer is None:
            self._producer = self._client().Producer({"bootstrap.servers": self._bootstrap_servers})
        return self._producer

    def publish(self, key: str, value: Mapping[str, Any]) -> None:
        """Publish one message with the region as the partition key (NFR-S2)."""
        producer = self._get_producer()
        producer.produce(
            self._topic,
            key=key.encode("utf-8"),
            value=json.dumps(value).encode("utf-8"),
        )
        producer.flush()

    def consume(self) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """Yield ``(key, value)`` pairs from the topic in arrival order."""
        consumer = self._client().Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": "climate_index",
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([self._topic])
        try:
            while True:
                message = consumer.poll(_CONSUME_POLL_TIMEOUT_S)
                if message is None or message.error():
                    continue
                key_bytes = message.key()
                key = key_bytes.decode("utf-8") if key_bytes is not None else ""
                value: Mapping[str, Any] = json.loads(message.value().decode("utf-8"))
                yield key, value
        finally:
            consumer.close()
