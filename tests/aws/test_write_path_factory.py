"""Write-path composition root: raw store, close-safety, and entry-point routing.

The processor and consumer entry points build both stores from config through the
factory, so ``CII_AGGREGATE_BACKEND=aws`` routes the write path to the S3 raw store
and the Iceberg-plus-DynamoDB fan-out without any code change. The AWS stores hold
no connection to close, so cleanup routes through :func:`close_if_supported`; these
tests prove that teardown never crashes on the missing ``close`` and that the
entry points build the AWS stores (monkeypatched, no real AWS, no moto).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from climate_index.adapters.aws.s3_raw_store import S3RawStore
from climate_index.adapters.composite import CompositeAggregateStore
from climate_index.adapters.duckdb import DuckDBRawStore
from climate_index.config import Settings
from climate_index.interfaces import RawStore
from climate_index.store_factory import build_raw_store, close_if_supported


def test_duckdb_backend_returns_duckdb_raw_store(tmp_path: Path) -> None:
    settings = Settings(aggregate_backend="duckdb", raw_store_path=tmp_path / "raw")
    store = build_raw_store(settings)
    assert isinstance(store, RawStore)
    assert isinstance(store, DuckDBRawStore)
    close_if_supported(store)


def test_aws_backend_returns_s3_raw_store_and_needs_no_close() -> None:
    # Construction touches no cloud SDK (the S3 client is lazy), so no moto needed.
    settings = Settings(
        aggregate_backend="aws",
        aws_region="us-east-1",
        raw_s3_bucket="climate-index-raw",
    )
    store = build_raw_store(settings)
    assert isinstance(store, RawStore)
    assert isinstance(store, S3RawStore)
    # The S3 raw store holds no connection: it exposes no close, and the shared
    # cleanup helper is a safe no-op for it (never raises).
    assert not hasattr(store, "close")
    close_if_supported(store)


def test_close_if_supported_closes_a_connection_backed_store() -> None:
    class Fake:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake = Fake()
    close_if_supported(fake)
    assert fake.closed is True


def test_processor_main_on_aws_builds_fanout_and_survives_teardown(monkeypatch: Any) -> None:
    # The processor entry point must build the AWS fan-out and S3 raw store from
    # config and tear them down without a close on either. Stub the run and the
    # producer so no event and no AWS call is needed; assert on what was built.
    import climate_index.processor as processor

    settings = Settings(
        aggregate_backend="aws",
        aws_region="us-east-1",
        iceberg_warehouse_bucket="climate-index-warehouse",
        iceberg_catalog_properties={"type": "glue"},
        dynamo_table="climate-index-serving",
        raw_s3_bucket="climate-index-raw",
    )
    monkeypatch.setattr(processor, "get_settings", lambda: settings)
    monkeypatch.setattr(processor, "run_producer", lambda *a, **k: 0)
    # main()'s post-run read-back would query real DynamoDB; stub the fan-out read
    # so the test stays offline while still exercising the real built store type.
    monkeypatch.setattr(CompositeAggregateStore, "read_region_series", lambda self, region: [])

    built: dict[str, Any] = {}

    def fake_run_processor(transport: Any, agg: Any, raw: Any, *a: Any, **k: Any) -> int:
        built["agg"] = agg
        built["raw"] = raw
        return 0

    monkeypatch.setattr(processor, "run_processor", fake_run_processor)

    processor.main()

    assert isinstance(built["agg"], CompositeAggregateStore)
    assert isinstance(built["raw"], S3RawStore)


def test_consumer_loop_oneshot_drains_once(monkeypatch: Any) -> None:
    from climate_index import consumer

    settings = Settings(aggregate_backend="duckdb", consumer_oneshot=True)
    calls = {"runs": 0, "naps": 0}

    def fake_once(*a: Any, **k: Any) -> Any:
        calls["runs"] += 1
        return None

    monkeypatch.setattr(consumer, "run_consumer_once", fake_once)
    passes = consumer.run_consumer_loop(
        consumer=object(),  # type: ignore[arg-type]
        aggregate_store=object(),  # type: ignore[arg-type]
        raw_store=object(),  # type: ignore[arg-type]
        settings=settings,
        sleep=lambda _s: calls.__setitem__("naps", calls["naps"] + 1),
    )
    assert passes == 1
    assert calls["runs"] == 1
    assert calls["naps"] == 0  # oneshot never idles


def test_consumer_loop_service_mode_loops_until_stopped(monkeypatch: Any) -> None:
    from climate_index import consumer

    settings = Settings(aggregate_backend="duckdb", consumer_oneshot=False)
    state = {"runs": 0}

    def fake_once(*a: Any, **k: Any) -> Any:
        state["runs"] += 1
        return None

    # The injected sleep is the loop's only exit seam here: after three drains it
    # raises to stop the otherwise-infinite service loop, proving it keeps draining.
    def fake_sleep(_s: float) -> None:
        if state["runs"] >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(consumer, "run_consumer_once", fake_once)
    with contextlib.suppress(KeyboardInterrupt):
        consumer.run_consumer_loop(
            consumer=object(),  # type: ignore[arg-type]
            aggregate_store=object(),  # type: ignore[arg-type]
            raw_store=object(),  # type: ignore[arg-type]
            settings=settings,
            sleep=fake_sleep,
        )
    assert state["runs"] == 3
