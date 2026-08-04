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
    """The event kinds carried on the single transport topic (E-4, FR-2)."""

    WEATHER = "weather"
    SATELLITE = "satellite"
    STATION = "station"


class Construction(StrEnum):
    """How a provider built the hourly station value (E-8).

    Recorded, never gated on. The measurement uncertainty the later comparison
    uses was derived for provider-validated hourly data, and one network supplies
    sub-hourly samples that OpenAQ means into an hour instead. Excluding that
    network after seeing it would be the move the licence rule already had to
    correct, so the difference is carried as an attribute and reported.
    """

    PROVIDER_HOURLY = "PROVIDER_HOURLY"
    COMPUTED_MEAN = "COMPUTED_MEAN"


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
    """E-2 WeatherEvent: one weather reading for a region.

    The shape does not vary by source (UC-1): the simulated source samples a
    plausible range, the real source carries a fetched reading.
    """

    model_config = ConfigDict(extra="forbid")

    ts: UtcDatetime
    region: RegionCode
    temperature_c: float
    rainfall_mm: float = Field(ge=0)
    wind_speed_ms: float = Field(ge=0)


class SatelliteEvent(BaseModel):
    """E-3 SatelliteEvent: one atmospheric-composition reading for a region.

    Named satellite on the wire for continuity of E-4 and the store schema. Under
    the real source it carries modeled atmospheric composition (an aerosol optical
    depth) with observed cloud cover, and a vegetation value that is a configured
    monthly reference rather than a measurement; see the E-3 provenance note in
    the specification. The field shapes do not vary by source.
    """

    model_config = ConfigDict(extra="forbid")

    ts: UtcDatetime
    region: RegionCode
    # E-7 sampling point. The contract freezes the comparison at city granularity,
    # so the model side has to carry a city: a station is compared against the
    # model value for its own city and only then aggregated to the region-window.
    # The adapter already fetches one reading per city and previously discarded
    # which one it was, which left the model half of a city-window unrecoverable
    # from the emitted stream. The field follows mechanically from a frozen rule,
    # as E-4's third member and the aggregate model PM2.5 field did.
    #
    # WeatherEvent deliberately does not gain it: the index reads weather at
    # region granularity and no comparison is made against it.
    city: str
    cloud_cover_pct: float = Field(ge=0, le=100)
    vegetation_index: float = Field(ge=-1, le=1)
    aerosol_index: float
    # E-3: the model analysis of surface PM2.5 mass concentration. Required, so
    # the adapter refuses to emit rather than substituting, which is what carries
    # ADR-0007's no-fabrication rule. Non-negative because a mass concentration
    # cannot be below zero; the provider was probed over 26496 hours across the
    # twelve configured cities and returned no negative and no null, with a
    # minimum of exactly zero. Unlike a station reading, which can go negative
    # near the detection limit, this is a modelled quantity floored at zero.
    model_pm25_ugm3: float = Field(ge=0)


class StationObservation(BaseModel):
    """E-8 StationObservation: one ground-station hour, for comparison only.

    Never an input to the index. Its absence lowers the provenance tier of a
    window (E-11), not the window's confidence grade (NFR-DQ2) and not any
    component metric; the specification freezes that boundary and UC-3 states it.

    ``pm25_ugm3`` carries no lower bound on purpose. Real instruments report
    negative values near the detection limit, and the frozen rules retain them:
    discarding or clamping would bias the station value upward exactly where the
    later tolerance floor dominates, which would move a measured difference for a
    reason that is not a difference. Validity is decided by the provider's own
    quality flag and by at least one underlying sample, both applied in the
    adapter, so nothing here invents a cutoff.
    """

    model_config = ConfigDict(extra="forbid")

    ts: UtcDatetime
    region: RegionCode
    city: str
    station_id: str
    pm25_ugm3: float
    sample_count: int = Field(ge=1)
    construction: Construction


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
    def wrap(cls, event: WeatherEvent | SatelliteEvent | StationObservation) -> EventEnvelope:
        """Wrap a typed event in a region-keyed envelope (UC-1, NFR-S2)."""
        if isinstance(event, WeatherEvent):
            event_type = EventType.WEATHER
        elif isinstance(event, SatelliteEvent):
            event_type = EventType.SATELLITE
        else:
            event_type = EventType.STATION
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
    # E-5: the mean model PM2.5 across the window's satellite events. Nullable,
    # because a window with no satellite event has none and because every row
    # written before this field existed carries none; backfilling the shipped
    # index is out of scope. A reported summary, not the input to the
    # disagreement comparison, which is evaluated at city granularity.
    model_pm25_ugm3: float | None = None


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
