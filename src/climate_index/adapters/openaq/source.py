"""Fetches ground-station PM2.5 hours from OpenAQ (UC-1, FR-11, E-8).

The second real source, behind the same single-method ``EventSource`` Protocol as
the Open-Meteo adapter and selected the same way. It emits
:class:`StationObservation`, which is never an index input: its absence lowers a
window's provenance tier, not its confidence grade and not any component metric.

Like the Open-Meteo adapter, the HTTP client is imported lazily inside the run
path, so importing the source factory pulls in no client (INV-6), and no endpoint
or key literal appears here: both arrive through the settings object from the
environment (INV-1).

The no-fabrication rule of ADR-0007 applies unchanged. An hour that fails to
arrive, that the provider has flagged, or that rests on no underlying sample
produces no event and is counted. Nothing is substituted and nothing is retried
in a loop.

What this module does not do: fetch a model value, or bring a station value
together with one. Reconciliation is a later task and the holdout is sealed until
then.

Rate limits are published at 60 requests a minute and 2000 an hour, with 429 on
exceed and a documented risk of a ban for repeatedly exceeding, so calls are
paced below the per-minute limit and a 429 is a counted miss rather than a retry.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from climate_index.config import Settings
from climate_index.core.models import Construction, StationObservation
from climate_index.logging_utils import StructuredLogger, get_logger

_PM25 = "pm25"
_HOUR = timedelta(hours=1)

# Why an hour was not emitted. Logged as a counter reason, never as a payload,
# and deliberately distinct from one another: a provider flag, an empty rollup
# and a transport failure are different causes, and folding them together would
# make one look like another.
_REASON_TRANSPORT = "transport_error"
_REASON_TIMEOUT = "timeout"
_REASON_STATUS = "http_status"
_REASON_RATE_LIMITED = "rate_limited"
_REASON_MALFORMED = "malformed_payload"
_REASON_NO_HOUR = "no_hour_returned"
_REASON_FLAGGED = "provider_flagged"
_REASON_NO_SAMPLES = "no_underlying_sample"
_REASON_MISSING_FIELD = "missing_field"
_REASON_SCHEMA = "schema_rejected"


@dataclass(frozen=True)
class AdmittedSensor:
    """One PM2.5 sensor admitted by the frozen station rules.

    Produced by applying the rules in ``PREREGISTRATION.md``: reference grade,
    fixed, within the radius of the model grid point, and covering the capture
    window. Held as data rather than recomputed per tick, because discovery costs
    roughly three hundred calls and the rules are stable between runs.
    """

    sensor_id: int
    station_id: str
    city: str
    region: str


class OpenAQStationSource:
    """Fetches one settled hour of station PM2.5 for the admitted sensors."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        sensors: Sequence[AdmittedSensor],
        lag_hours: int,
        timeout_s: float = 10.0,
        pace_s: float = 1.1,
        logger: StructuredLogger | None = None,
        transport: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._sensors = tuple(sensors)
        self._lag = timedelta(hours=lag_hours)
        self._timeout_s = timeout_s
        self._pace_s = pace_s
        self._log = logger if logger is not None else get_logger("openaq_source")
        self._transport = transport
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._missing = 0
        self._last_call = 0.0

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        sensors: Sequence[AdmittedSensor],
        *,
        logger: StructuredLogger | None = None,
        transport: Any | None = None,
    ) -> OpenAQStationSource:
        """Build from configuration, refusing loudly on a missing setting.

        The backend defaults to off and both of these default to ``None``, so the
        next person to enable the adapter meets exactly this. Naming the setting
        here is the difference between a fixable message and a ``None`` surfacing
        three frames down inside an HTTP client.
        """
        if settings.openaq_base_url is None:
            raise ValueError(
                "CII_OPENAQ_BASE_URL is not set, and the OpenAQ station source needs it. "
                "No endpoint literal lives in source (INV-1); set it in the environment."
            )
        if not settings.openaq_api_key:
            raise ValueError(
                "CII_OPENAQ_API_KEY is not set, and the OpenAQ station source needs it. "
                "It is a secret: supply it through the environment, never in a tracked file."
            )
        return cls(
            base_url=settings.openaq_base_url,
            api_key=settings.openaq_api_key,
            sensors=sensors,
            lag_hours=settings.station_analysis_lag_hours,
            timeout_s=settings.source_fetch_timeout_s,
            logger=logger,
            transport=transport,
        )

    @property
    def missing_count(self) -> int:
        """Hours that could not be emitted, for any reason, since construction."""
        return self._missing

    @staticmethod
    def _client_module() -> Any:
        """Import the HTTP client lazily (the single import site in this module).

        Typed Any rather than ModuleType, matching the Open-Meteo adapter: the
        pre-commit mypy hook runs in an isolated environment without httpx, so a
        ModuleType annotation there is a Returning-Any error even though the
        project venv types it fine.
        """
        import httpx

        return httpx

    def _skip(self, reason: str, sensor: AdmittedSensor, **fields: Any) -> None:
        self._missing += 1
        self._log.event(
            "station_reading_unavailable",
            reason=reason,
            region=sensor.region,
            city=sensor.city,
            station=sensor.station_id,
            **fields,
        )

    def settled_hour(self) -> datetime:
        """The most recent hour old enough to be admitted under the frozen lag."""
        now = self._clock().astimezone(UTC)
        boundary = now.replace(minute=0, second=0, microsecond=0) - self._lag
        return boundary

    def fetch_tick(self) -> Sequence[StationObservation]:
        """One settled hour of station observations, one per admitted sensor."""
        hour = self.settled_hour()
        httpx = self._client_module()
        events: list[StationObservation] = []
        client_args: dict[str, Any] = {"timeout": self._timeout_s}
        if self._transport is not None:
            client_args["transport"] = self._transport
        with httpx.Client(**client_args) as client:
            for sensor in self._sensors:
                observation = self._fetch_one(client, httpx, sensor, hour)
                if observation is not None:
                    events.append(observation)
        return events

    def _pace(self) -> None:
        wait = self._pace_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def _fetch_one(
        self, client: Any, httpx: Any, sensor: AdmittedSensor, hour: datetime
    ) -> StationObservation | None:
        url = f"{self._base_url}/sensors/{sensor.sensor_id}/hours"
        params = {
            "datetime_from": hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "datetime_to": (hour + _HOUR).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": "1",
        }
        if self._pace_s:
            self._pace()
        try:
            response = client.get(url, params=params, headers={"X-API-Key": self._api_key})
        except httpx.TimeoutException:
            self._skip(_REASON_TIMEOUT, sensor)
            return None
        except httpx.HTTPError:
            self._skip(_REASON_TRANSPORT, sensor)
            return None
        finally:
            self._last_call = time.monotonic()

        if response.status_code == 429:
            # Counted, never retried in a loop: the documented consequence of
            # repeatedly exceeding the limit is a ban.
            self._skip(_REASON_RATE_LIMITED, sensor)
            return None
        if response.status_code != 200:
            self._skip(_REASON_STATUS, sensor, status=response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            self._skip(_REASON_MALFORMED, sensor)
            return None
        return self._build(payload, sensor, hour)

    def _build(
        self, payload: Any, sensor: AdmittedSensor, hour: datetime
    ) -> StationObservation | None:
        if not isinstance(payload, dict):
            self._skip(_REASON_MALFORMED, sensor)
            return None
        results = payload.get("results") or []
        if not results:
            # An hour the provider simply does not have. Absent, not zero.
            self._skip(_REASON_NO_HOUR, sensor, hour=hour.isoformat())
            return None
        row = results[0]
        if not isinstance(row, dict):
            self._skip(_REASON_MALFORMED, sensor)
            return None

        flag_info = row.get("flagInfo") or {}
        if flag_info.get("hasFlags"):
            # The provider's own quality flag is the external authority on
            # validity, which is why no cutoff of this project's own invention
            # appears anywhere in this file.
            self._skip(_REASON_FLAGGED, sensor, hour=hour.isoformat())
            return None

        coverage = row.get("coverage") or {}
        observed = coverage.get("observedCount")
        if not isinstance(observed, int) or observed < 1:
            self._skip(_REASON_NO_SAMPLES, sensor, hour=hour.isoformat())
            return None

        value = row.get("value")
        if not isinstance(value, int | float):
            self._skip(_REASON_MISSING_FIELD, sensor, field="value")
            return None

        try:
            return StationObservation(
                ts=hour,
                region=sensor.region,
                city=sensor.city,
                station_id=sensor.station_id,
                # Negative readings are retained. Clamping would bias the value
                # upward exactly where the later tolerance floor dominates.
                pm25_ugm3=float(value),
                sample_count=observed,
                construction=(
                    Construction.PROVIDER_HOURLY if observed == 1 else Construction.COMPUTED_MEAN
                ),
            )
        except ValidationError:
            self._skip(_REASON_SCHEMA, sensor)
            return None
