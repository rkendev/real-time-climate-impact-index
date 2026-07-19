"""Kafka adapter tests: Protocol conformance and lazy-import safety.

The lazy-import proof is the key T2 guarantee: importing the producer and the
Kafka adapter modules must pull in no Kafka client, so test collection and
``make run_producer`` (no broker) never touch it. The live publish/consume test
is deferred until infra is up and is skipped here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from climate_index.adapters.kafka import KafkaCommittableConsumer, KafkaTransport
from climate_index.interfaces import CommittableConsumer, Transport

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the interpreter in the repo with a broker-free, src-on-path env."""
    env = {k: v for k, v in os.environ.items() if k != "CII_TRANSPORT_BOOTSTRAP_SERVERS"}
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_kafka_transport_satisfies_protocol() -> None:
    assert isinstance(KafkaTransport("broker-placeholder"), Transport)


def test_kafka_committable_consumer_satisfies_protocol() -> None:
    assert isinstance(KafkaCommittableConsumer("broker-placeholder"), CommittableConsumer)


def test_importing_producer_and_adapter_pulls_in_no_kafka_client() -> None:
    code = (
        "import sys\n"
        "import climate_index.producer\n"
        "import climate_index.consumer\n"
        "import climate_index.adapters.kafka.transport\n"
        "climate_index.adapters.kafka.transport.KafkaCommittableConsumer('broker-placeholder')\n"
        "roots = ('kafka', 'confluent_kafka', 'aiokafka')\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in roots]\n"
        "assert not bad, bad\n"
    )
    result = _run(["-c", code])
    assert result.returncode == 0, result.stderr


def test_run_producer_main_is_a_safe_noop_without_a_broker() -> None:
    result = _run(["-m", "climate_index.producer"])
    assert result.returncode == 0, result.stderr
    assert "no_broker_configured" in result.stdout
    assert "kafka" not in result.stderr.lower()


@pytest.mark.skip(reason="requires a running broker; deferred to the infra track")
def test_live_kafka_publish_consume_roundtrip() -> None:  # pragma: no cover
    transport = KafkaTransport("broker-placeholder")
    transport.publish("EUR", {"n": 1})
    assert next(transport.consume()) == ("EUR", {"n": 1})


@pytest.mark.skip(reason="requires a running broker; deferred to the infra track")
def test_live_kafka_commit_after_write_recovery() -> None:  # pragma: no cover
    # The live proof of ADR-0002 against a real broker: consume a window, write
    # its aggregate, commit, then restart and assert no reprocessing. The
    # brokerless equivalent runs in test_consumer_recovery.py.
    consumer = KafkaCommittableConsumer("broker-placeholder")
    offset, key, _value = next(consumer.poll())
    assert key == "EUR"
    consumer.commit(offset)
