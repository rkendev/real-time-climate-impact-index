"""Plain S3 raw store adapter (UC-4, FR-7).

An append-only audit trail of validated raw events. Each event is written as one
newline-delimited JSON object under a config-driven prefix, with a unique
per-event key so distinct events never collide. Raw is deliberately not
deduplicated: only the aggregate-of-record needs idempotency (NFR-R1), so a replay
may re-append the same event, which is acceptable for an audit trail. There is no
MERGE and no Iceberg here (ADR-0003, as clarified for P2-T1); the raw store is
plain S3, a separate target from the aggregate-of-record.

``boto3`` is imported lazily in the run path, so importing this module pulls in no
cloud SDK. The bucket, prefix, region, and optional endpoint override all come
from config (INV-1).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from climate_index.adapters.aws._keys import canonical_window_key

if TYPE_CHECKING:
    from climate_index.config import Settings


class S3RawStore:
    """Append-only S3 audit trail for validated raw events (FR-7)."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "raw",
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._region = region
        self._endpoint_url = endpoint_url
        self._client_cache: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> S3RawStore:
        """Build the adapter from config (INV-1); no literal bucket or endpoint."""
        if settings.raw_s3_bucket is None:
            raise ValueError("CII_RAW_S3_BUCKET is not configured")
        return cls(
            bucket=settings.raw_s3_bucket,
            prefix=settings.raw_s3_prefix,
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

    def _client(self) -> Any:
        """Load and cache the S3 client (lazy SDK import)."""
        if self._client_cache is None:
            import boto3

            self._client_cache = boto3.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            )
        return self._client_cache

    def _key_for(self, event: Mapping[str, Any]) -> str:
        """A unique object key: <prefix>/<region>/<window-or-ts>/<uuid>.json."""
        region = str(event.get("region", "unknown"))
        moment = event.get("ts")
        segment = canonical_window_key(moment) if moment is not None else "unknown"
        return f"{self._prefix}/{region}/{segment}/{uuid4().hex}.json"

    def append(self, event: Mapping[str, Any]) -> None:
        """Append one validated event as a newline-delimited JSON object.

        Append-only: a unique key per call means a replay re-appends rather than
        overwriting, which is the intended audit behavior (raw is not
        deduplicated).
        """
        body = json.dumps(event, default=str, sort_keys=True).encode("utf-8") + b"\n"
        self._client().put_object(Bucket=self._bucket, Key=self._key_for(event), Body=body)
