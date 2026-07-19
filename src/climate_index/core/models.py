"""Entity models and runtime schema contracts (E-1..E-6, NFR-T1).

These pydantic models are the ingest contract: every event and record is
validated field by field at runtime and in tests. They are pure, vendor-free
domain data (INV-4), so they live under ``core`` and import no transport or
store client. The region set and the structural constants remain the sole
authority of :mod:`climate_index.config`; nothing here re-declares them.

Per-record validation via these models is the contract for NFR-T1. A batch or
dataframe contract is deferred to the persistence track.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from climate_index.config import get_settings


def _validate_region(value: str) -> str:
    """Accept a region only if it is in the configured set (E-1, NFR-S1)."""
    allowed = get_settings().region_list
    if value not in allowed:
        raise ValueError(f"region not in configured set {allowed}: {value!r}")
    return value


def _require_utc(value: datetime) -> datetime:
    """Accept only a timezone-aware datetime at a zero UTC offset.

    Naive datetimes and non-UTC offsets are rejected so every timestamp on the
    transport and in the store is unambiguously UTC (E-2, E-3, E-5).
    """
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


# E-1 RegionCode: a region string validated against the configured set. There is
# deliberately no second region list; membership is decided by config alone.
RegionCode = Annotated[str, AfterValidator(_validate_region)]

# A UTC-enforced timestamp, reused by every event and aggregate-record field.
UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class EventType(StrEnum):
    """The two event kinds carried on the single transport topic (E-4, FR-2)."""

    WEATHER = "weather"
    SATELLITE = "satellite"


class Confidence(StrEnum):
    """Provenance-graded confidence for an aggregate row (E-5, NFR-DQ2)."""

    MEASURED = "MEASURED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class ReasonCode(StrEnum):
    """Why an event failed the validation gate (E-6, FR-3)."""

    SCHEMA = "schema"
    RANGE = "range"
    PARSE = "parse"


class WeatherEvent(BaseModel):
    """E-2 WeatherEvent: one synthetic weather reading for a region."""

    model_config = ConfigDict(extra="forbid")

    ts: UtcDatetime
    region: RegionCode
    temperature_c: float
    rainfall_mm: float = Field(ge=0)
    wind_speed_ms: float = Field(ge=0)


class SatelliteEvent(BaseModel):
    """E-3 SatelliteEvent: one synthetic satellite reading for a region."""

    model_config = ConfigDict(extra="forbid")

    ts: UtcDatetime
    region: RegionCode
    cloud_cover_pct: float = Field(ge=0, le=100)
    vegetation_index: float = Field(ge=-1, le=1)
    aerosol_index: float


class EventEnvelope(BaseModel):
    """E-4 EventEnvelope: the single message shape on the transport (FR-2).

    ``key`` is the region partition key (NFR-S2). ``payload`` is the loosely
    typed event body; validating it against the schema for ``event_type`` is the
    validation gate's job (UC-2), which keeps the envelope itself the one message
    shape every consumer parses first.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    key: RegionCode
    payload: dict[str, Any]

    @classmethod
    def wrap(cls, event: WeatherEvent | SatelliteEvent) -> EventEnvelope:
        """Wrap a typed event in a region-keyed envelope (UC-1, NFR-S2)."""
        event_type = EventType.WEATHER if isinstance(event, WeatherEvent) else EventType.SATELLITE
        return cls(
            event_type=event_type,
            key=event.region,
            payload=event.model_dump(mode="json"),
        )


class ClimateIndexRecord(BaseModel):
    """E-5 ClimateIndexRecord: one aggregate row per region per closed window.

    Natural key ``(region, window_start, window_end)``; writes are idempotent on
    it (FR-6, NFR-R1). The computation that fills these fields lands in a later
    track; this model is the schema contract only.
    """

    model_config = ConfigDict(extra="forbid")

    region: RegionCode
    window_start: UtcDatetime
    window_end: UtcDatetime
    impact_index: float = Field(ge=0, le=100)
    temperature_anomaly: float
    dryness_index: float
    pollution_index: float
    confidence: Confidence


class QuarantineRecord(BaseModel):
    """E-6 QuarantineRecord: an event that failed validation (FR-3, INV-3).

    ``event_type`` is the *claimed* type kept as a plain string so an invalid
    type is still recordable. ``raw`` is retained for audit only and is never
    fed downstream.
    """

    model_config = ConfigDict(extra="forbid")

    ts_received: UtcDatetime
    event_type: str
    reason_code: ReasonCode
    raw: dict[str, Any]
