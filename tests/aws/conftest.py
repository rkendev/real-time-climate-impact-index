"""Offline AWS test harness: a local moto server for S3 and DynamoDB (no spend).

Every AWS adapter test runs against a real localhost moto server, not in-process
moto, because pyiceberg's PyArrow S3 file IO uses the AWS C++ SDK, which the
in-process botocore monkeypatch does not intercept. A session-scoped fixture
starts the server, sets fake credentials and the region, and (before any adapter
test) does a trivial put and get through the PyArrow S3 file IO over plain HTTP,
so a misconfigured endpoint fails loudly and early rather than deep inside a
MERGE. The moto server speaks http; PyArrow S3 IO defaults to https, so the
endpoint is passed with an explicit http scheme (the ARROW-16437 symptom).

Each test gets its own buckets, DynamoDB table, and SQLite catalog file, so tests
are isolated without resetting shared state.
"""

from __future__ import annotations

import itertools
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from climate_index.core.models import ClimateIndexRecord, Confidence

_REGION = "us-east-1"
_FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": _REGION,
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _healthcheck_pyarrow_s3(endpoint: str) -> None:
    """Put and get through the PyArrow S3 file IO so an http misconfig fails early."""
    import boto3
    import pyarrow.fs as pafs

    bucket = "cii-healthcheck"
    client = boto3.client("s3", endpoint_url=endpoint, region_name=_REGION)
    client.create_bucket(Bucket=bucket)
    filesystem = pafs.S3FileSystem(
        access_key="testing",
        secret_key="testing",
        endpoint_override=endpoint.removeprefix("http://"),
        scheme="http",
        region=_REGION,
    )
    path = f"{bucket}/healthcheck"
    with filesystem.open_output_stream(path) as stream:
        stream.write(b"ok")
    with filesystem.open_input_stream(path) as stream:
        if stream.read() != b"ok":
            raise RuntimeError("moto S3 PyArrow file IO healthcheck failed")


@pytest.fixture(scope="session", autouse=True)
def _aws_credentials() -> Iterator[None]:
    import os

    prior = {key: os.environ.get(key) for key in _FAKE_CREDENTIALS}
    os.environ.update(_FAKE_CREDENTIALS)
    yield
    for key, value in prior.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="session")
def moto_endpoint(_aws_credentials: None) -> Iterator[str]:
    from moto.server import ThreadedMotoServer

    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port)
    server.start()
    endpoint = f"http://127.0.0.1:{port}"
    try:
        _healthcheck_pyarrow_s3(endpoint)
        yield endpoint
    finally:
        server.stop()


@pytest.fixture(scope="session")
def _resource_counter() -> Any:
    return itertools.count()


@dataclass(frozen=True)
class AwsContext:
    """Per-test AWS resource names and the config-shaped adapter inputs."""

    endpoint: str
    region: str
    warehouse_bucket: str
    raw_bucket: str
    raw_prefix: str
    dynamo_table: str
    namespace: str
    table_name: str
    catalog_properties: dict[str, str]


@pytest.fixture()
def aws_ctx(
    moto_endpoint: str,
    _resource_counter: Any,
    tmp_path: Path,
) -> AwsContext:
    import boto3

    ordinal = next(_resource_counter)
    warehouse_bucket = f"cii-agg-{ordinal}"
    raw_bucket = f"cii-raw-{ordinal}"
    dynamo_table = f"cii-serving-{ordinal}"

    s3 = boto3.client("s3", endpoint_url=moto_endpoint, region_name=_REGION)
    s3.create_bucket(Bucket=warehouse_bucket)
    s3.create_bucket(Bucket=raw_bucket)

    dynamo = boto3.client("dynamodb", endpoint_url=moto_endpoint, region_name=_REGION)
    dynamo.create_table(
        TableName=dynamo_table,
        KeySchema=[
            {"AttributeName": "region", "KeyType": "HASH"},
            {"AttributeName": "window_start", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "region", "AttributeType": "S"},
            {"AttributeName": "window_start", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    catalog_properties = {
        "type": "sql",
        "uri": f"sqlite:///{tmp_path / 'catalog.db'}",
        "warehouse": f"s3://{warehouse_bucket}/wh",
        "s3.endpoint": moto_endpoint,
        "s3.access-key-id": "testing",
        "s3.secret-access-key": "testing",
        "s3.region": _REGION,
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    return AwsContext(
        endpoint=moto_endpoint,
        region=_REGION,
        warehouse_bucket=warehouse_bucket,
        raw_bucket=raw_bucket,
        raw_prefix="raw",
        dynamo_table=dynamo_table,
        namespace="climate_index",
        table_name="climate_index",
        catalog_properties=catalog_properties,
    )


@pytest.fixture()
def make_record() -> Any:
    """Return a factory for DuckDB-boundary-shaped aggregate record dicts.

    Records come from :class:`ClimateIndexRecord` dumped with ``mode="python"``,
    matching what the processor hands the store (a ``Confidence`` enum and
    timezone-aware UTC datetimes).
    """

    def _make(
        window_hour: int = 12,
        impact: float = 75.25,
        region: str = "EUR",
        confidence: Confidence = Confidence.MEASURED,
    ) -> dict[str, Any]:
        from datetime import UTC, datetime

        record = ClimateIndexRecord(
            region=region,
            window_start=datetime(2026, 7, 19, window_hour, 0, tzinfo=UTC),
            window_end=datetime(2026, 7, 19, window_hour, 30, tzinfo=UTC),
            impact_index=impact,
            temperature_anomaly=10.0,
            dryness_index=0.6,
            pollution_index=0.575,
            confidence=confidence,
        )
        return record.model_dump(mode="python")

    return _make
