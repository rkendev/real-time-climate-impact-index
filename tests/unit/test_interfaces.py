"""The in-memory transport satisfies the Transport interface (T-I1).

Confirms MemoryTransport structurally implements the Transport Protocol, the
publish/consume roundtrip preserves order, and published values are isolated
from later mutation of the caller's object.
"""

from __future__ import annotations

from climate_index.adapters.memory import MemoryTransport
from climate_index.interfaces import Transport


def test_memory_transport_satisfies_protocol() -> None:
    assert isinstance(MemoryTransport(), Transport)


def test_publish_consume_roundtrip_preserves_order() -> None:
    transport = MemoryTransport()
    transport.publish("EUR", {"n": 1})
    transport.publish("NAM", {"n": 2})
    assert list(transport.consume()) == [("EUR", {"n": 1}), ("NAM", {"n": 2})]
    assert len(transport) == 2


def test_published_value_is_isolated_from_caller_mutation() -> None:
    transport = MemoryTransport()
    payload = {"n": 1}
    transport.publish("EUR", payload)
    payload["n"] = 99
    assert list(transport.consume()) == [("EUR", {"n": 1})]
