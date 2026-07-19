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
        import confluent_kafka

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


class KafkaCommittableConsumer:
    """Kafka consumer with auto-commit disabled and explicit commit (ADR-0002).

    Structurally satisfies
    :class:`climate_index.interfaces.transport.CommittableConsumer`. The client
    import stays lazy (the single import site is :meth:`_client`), so importing
    this module pulls in no Kafka client and test collection never triggers the
    import chain; the live poll/commit test is deferred until infra is up.

    ``enable.auto.commit`` is ``False`` so offsets advance only through
    :meth:`commit`, which the recovery loop calls after the window's aggregate
    write has succeeded. Bootstrap servers arrive from config (INV-1); no endpoint
    literal appears here. Phase 1 assumes a single partition, so ``commit`` maps
    the processed offset onto the last polled message's partition.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = _DEFAULT_TOPIC,
        group_id: str = "climate_index",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._consumer: Any | None = None
        self._last_partition: int | None = None

    @staticmethod
    def _client() -> Any:
        """Import the Kafka client lazily (the single import site in this class)."""
        import confluent_kafka

        return confluent_kafka

    def _get_consumer(self) -> Any:
        """Lazily construct and subscribe the consumer on first poll."""
        if self._consumer is None:
            self._consumer = self._client().Consumer(
                {
                    "bootstrap.servers": self._bootstrap_servers,
                    "group.id": self._group_id,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": False,
                }
            )
            self._consumer.subscribe([self._topic])
        return self._consumer

    def poll(self) -> Iterator[tuple[int, str, Mapping[str, Any]]]:
        """Drain currently-available messages, yielding ``(offset, key, value)``."""
        consumer = self._get_consumer()
        while True:
            message = consumer.poll(_CONSUME_POLL_TIMEOUT_S)
            if message is None:
                break  # drained: no message within the poll timeout
            if message.error():
                continue
            self._last_partition = int(message.partition())
            key_bytes = message.key()
            key = key_bytes.decode("utf-8") if key_bytes is not None else ""
            value: Mapping[str, Any] = json.loads(message.value().decode("utf-8"))
            yield int(message.offset()), key, value

    def commit(self, offset: int) -> None:
        """Commit synchronously through ``offset`` on the last polled partition."""
        if self._last_partition is None:
            return
        client = self._client()
        topic_partition = client.TopicPartition(self._topic, self._last_partition, offset + 1)
        self._get_consumer().commit(offsets=[topic_partition], asynchronous=False)

    def close(self) -> None:
        """Close the consumer if it was opened."""
        if self._consumer is not None:
            self._consumer.close()
