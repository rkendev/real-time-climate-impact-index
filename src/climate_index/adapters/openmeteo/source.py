"""Open-Meteo EventSource adapter (UC-1, ADR-0007).

Structurally satisfies :class:`climate_index.interfaces.source.EventSource`. The
HTTP client import is lazy and lives inside the run path only, so importing this
module or its package pulls in no client and test collection never dials or
imports one, the same discipline the Kafka and cloud adapters follow.

Both endpoints arrive from config, populated from the environment (INV-1); no
URL literal appears here. The variable names below are query parameters and
response keys, not endpoints.

Two calls per city per tick, one per endpoint, deliberately not batched. The API
accepts comma-separated coordinate lists, which would cut a tick to two requests,
but then one failure erases a whole region's stream. One call per city means one
city failing costs one city, and independent failure domains are the point
(ADR-0007).

The no-fabrication rule governs everything here. A timeout, a transport error, a
non-success status, an error body, a missing or null field, or a payload that
fails model validation all mean the affected event is **not emitted**. Each is
logged with a structured reason and counted, and none is retried or replaced. A
gap is data about the feed, and the confidence grader is what reads it; hiding a
gap would corrupt a grade (NFR-DQ2).

Field mapping, verified against live responses rather than assumed:

* weather, from the forecast endpoint's ``current`` block: ``temperature_2m``
  (degrees C), ``precipitation`` (mm), ``wind_speed_10m`` (m/s, which is what
  ``wind_speed_unit=ms`` yields), and ``cloud_cover`` (percent). The current
  cloud variable is ``cloud_cover``; ``cloud_cover_total`` is rejected by the API
  with a 400.
* pollution, from the air quality endpoint's ``current`` block:
  ``aerosol_optical_depth`` (dimensionless).

Timestamps need care. Even with ``timezone=UTC`` the API returns a **naive** ISO
string with no offset and no trailing Z (``2026-07-22T11:30``), carrying the zero
offset separately in ``utc_offset_seconds``. The entity models reject naive
datetimes outright, so :func:`_parse_utc` attaches UTC explicitly, and only after
confirming the response really did answer at a zero offset. Blindly stamping UTC
onto a value the API said was local would silently shift every reading.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from climate_index.core.models import SatelliteEvent, WeatherEvent
from climate_index.logging_utils import StructuredLogger, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import httpx

    from climate_index.config import CityLocation, Settings

# Forecast endpoint current-block variables, in request order.
_WEATHER_CURRENT = ("temperature_2m", "precipitation", "wind_speed_10m", "cloud_cover")
# Air quality endpoint current-block variables.
_AIR_QUALITY_CURRENT = ("aerosol_optical_depth",)

# Shared query parameters. Wind in metres per second so no conversion is needed,
# and UTC so the returned clock needs no zone lookup (only the explicit tzinfo
# attach in _parse_utc, which checks utc_offset_seconds first).
_WIND_SPEED_UNIT = "ms"
_TIMEZONE = "UTC"

# Why an event was not emitted. Logged as a counter reason, never as a payload.
_REASON_TRANSPORT = "transport_error"
_REASON_TIMEOUT = "timeout"
_REASON_STATUS = "http_status"
_REASON_ERROR_BODY = "provider_error"
_REASON_MALFORMED = "malformed_payload"
_REASON_MISSING_FIELD = "missing_field"
_REASON_OFFSET = "non_utc_offset"
_REASON_SCHEMA = "schema_rejected"


class OpenMeteoEventSource:
    """Fetches real weather and air quality readings for the configured cities."""

    def __init__(
        self,
        *,
        weather_url: str,
        air_quality_url: str,
        locations: Mapping[str, Sequence[CityLocation]],
        monthly_vegetation: Mapping[str, Sequence[float]],
        regions: Sequence[str],
        timeout_s: float,
        logger: StructuredLogger | None = None,
        transport: Any | None = None,
    ) -> None:
        self._weather_url = weather_url
        self._air_quality_url = air_quality_url
        self._locations = locations
        self._monthly_vegetation = monthly_vegetation
        self._regions = tuple(regions)
        self._timeout_s = timeout_s
        self._log = logger if logger is not None else get_logger("openmeteo_source")
        # Only tests pass a transport (httpx.MockTransport), which is how the
        # adapter is exercised without a network. Production leaves it None.
        self._transport = transport
        self._missing = 0

        for region in self._regions:
            if not self._locations.get(region):
                raise ValueError(f"no configured locations for region {region!r} (E-7)")
            if len(self._monthly_vegetation.get(region, ())) != 12:
                raise ValueError(f"no monthly vegetation reference for region {region!r} (E-3)")

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        regions: Sequence[str] | None = None,
        *,
        logger: StructuredLogger | None = None,
        transport: Any | None = None,
    ) -> OpenMeteoEventSource:
        """Build from config, refusing rather than guessing when an endpoint is unset."""
        if settings.open_meteo_weather_url is None or settings.open_meteo_air_quality_url is None:
            raise ValueError(
                "the real source needs CII_OPEN_METEO_WEATHER_URL and "
                "CII_OPEN_METEO_AIR_QUALITY_URL to be set (INV-1)"
            )
        return cls(
            weather_url=settings.open_meteo_weather_url,
            air_quality_url=settings.open_meteo_air_quality_url,
            locations=settings.region_locations,
            monthly_vegetation=settings.region_monthly_vegetation,
            regions=regions if regions is not None else settings.region_list,
            timeout_s=settings.source_fetch_timeout_s,
            logger=logger,
            transport=transport,
        )

    @property
    def missing_count(self) -> int:
        """How many events were not emitted because a reading was unavailable."""
        return self._missing

    @staticmethod
    def _client_module() -> Any:
        """Import the HTTP client lazily (the single import site in this module)."""
        import httpx

        return httpx

    def _open_client(self) -> httpx.Client:
        """Open a client for one fetch pass, with the configured timeout."""
        module = self._client_module()
        if self._transport is not None:
            client = module.Client(timeout=self._timeout_s, transport=self._transport)
        else:
            client = module.Client(timeout=self._timeout_s)
        # The module is Any because its import is lazy, so the narrowing that
        # the annotation promises happens here rather than at the import site.
        return cast("httpx.Client", client)

    def _skip(self, reason: str, region: str, city: str, stream: str, **extra: Any) -> None:
        """Record one event that will not be emitted (metadata only, NFR-O3)."""
        self._missing += 1
        self._log.event(
            "source_reading_unavailable",
            level=logging.WARNING,
            reason=reason,
            region=region,
            city=city,
            stream=stream,
            **extra,
        )

    def _get(
        self,
        client: httpx.Client,
        url: str,
        params: dict[str, Any],
        region: str,
        city: str,
        stream: str,
    ) -> dict[str, Any] | None:
        """GET one payload, or None with a logged reason. Never raises, never retries."""
        httpx = self._client_module()
        try:
            response = client.get(url, params=params)
        except httpx.TimeoutException:
            self._skip(_REASON_TIMEOUT, region, city, stream)
            return None
        except httpx.HTTPError:
            self._skip(_REASON_TRANSPORT, region, city, stream)
            return None

        if response.status_code != 200:
            self._skip(_REASON_STATUS, region, city, stream, status=response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            self._skip(_REASON_MALFORMED, region, city, stream)
            return None
        if not isinstance(payload, dict):
            self._skip(_REASON_MALFORMED, region, city, stream)
            return None
        if payload.get("error"):
            self._skip(_REASON_ERROR_BODY, region, city, stream)
            return None
        return payload

    def _weather_params(
        self, city: CityLocation, block: str, extra: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "latitude": city.latitude,
            "longitude": city.longitude,
            block: ",".join(_WEATHER_CURRENT),
            "wind_speed_unit": _WIND_SPEED_UNIT,
            "timezone": _TIMEZONE,
            **extra,
        }

    def _air_quality_params(
        self, city: CityLocation, block: str, extra: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "latitude": city.latitude,
            "longitude": city.longitude,
            block: ",".join(_AIR_QUALITY_CURRENT),
            "timezone": _TIMEZONE,
            **extra,
        }

    def fetch_tick(self) -> list[WeatherEvent | SatelliteEvent]:
        """Fetch one reading per stream per configured city (UC-1).

        Two GETs per city, one per endpoint. A city that fails contributes
        nothing and thins its region's window; it never blocks another city and
        never yields a substituted value.
        """
        events: list[WeatherEvent | SatelliteEvent] = []
        with self._open_client() as client:
            for region in self._regions:
                for city in self._locations[region]:
                    events.extend(self._fetch_city(client, region, city))
        self._log.event(
            "source_tick_complete",
            regions=len(self._regions),
            emitted=len(events),
            unavailable=self._missing,
        )
        return events

    def _fetch_city(
        self, client: httpx.Client, region: str, city: CityLocation
    ) -> list[WeatherEvent | SatelliteEvent]:
        """Both readings for one city, each omitted independently on failure."""
        events: list[WeatherEvent | SatelliteEvent] = []

        weather_payload = self._get(
            client,
            self._weather_url,
            self._weather_params(city, "current", {}),
            region,
            city.name,
            "weather",
        )
        air_payload = self._get(
            client,
            self._air_quality_url,
            self._air_quality_params(city, "current", {}),
            region,
            city.name,
            "satellite",
        )

        weather_block = self._current_block(weather_payload, region, city.name, "weather")
        if weather_block is not None:
            ts = self._parse_current_ts(
                weather_payload, weather_block, region, city.name, "weather"
            )
            if ts is not None:
                weather = self._build_weather(weather_block, ts, region, city.name)
                if weather is not None:
                    events.append(weather)

        # The satellite-stream event needs BOTH calls: its cloud cover comes from
        # the forecast payload and its aerosol value from the air quality one, so
        # either call failing means this city contributes no pollution reading.
        air_block = self._current_block(air_payload, region, city.name, "satellite")
        if weather_block is not None and air_block is not None:
            air_ts = self._parse_current_ts(air_payload, air_block, region, city.name, "satellite")
            if air_ts is not None:
                satellite = self._build_satellite(
                    cloud_cover=weather_block.get("cloud_cover"),
                    aerosol=air_block.get("aerosol_optical_depth"),
                    ts=air_ts,
                    region=region,
                    city=city.name,
                )
                if satellite is not None:
                    events.append(satellite)

        return events

    def _current_block(
        self, payload: dict[str, Any] | None, region: str, city: str, stream: str
    ) -> dict[str, Any] | None:
        if payload is None:
            return None
        block = payload.get("current")
        if not isinstance(block, dict):
            self._skip(_REASON_MISSING_FIELD, region, city, stream, field="current")
            return None
        return block

    def _parse_current_ts(
        self,
        payload: dict[str, Any] | None,
        block: dict[str, Any],
        region: str,
        city: str,
        stream: str,
    ) -> datetime | None:
        assert payload is not None  # guarded by the caller
        raw = block.get("time")
        if not isinstance(raw, str):
            self._skip(_REASON_MISSING_FIELD, region, city, stream, field="time")
            return None
        offset = payload.get("utc_offset_seconds")
        if offset != 0:
            # The response is not on the UTC clock the request asked for.
            # Stamping UTC anyway would shift every reading silently.
            self._skip(_REASON_OFFSET, region, city, stream)
            return None
        try:
            return _parse_utc(raw)
        except ValueError:
            self._skip(_REASON_MALFORMED, region, city, stream, field="time")
            return None

    def _build_weather(
        self, block: Mapping[str, Any], ts: datetime, region: str, city: str
    ) -> WeatherEvent | None:
        values = _required_floats(block, ("temperature_2m", "precipitation", "wind_speed_10m"))
        if values is None:
            self._skip(_REASON_MISSING_FIELD, region, city, "weather")
            return None
        try:
            return WeatherEvent(
                ts=ts,
                region=region,
                temperature_c=values["temperature_2m"],
                rainfall_mm=values["precipitation"],
                wind_speed_ms=values["wind_speed_10m"],
            )
        except ValidationError:
            self._skip(_REASON_SCHEMA, region, city, "weather")
            return None

    def _build_satellite(
        self,
        *,
        cloud_cover: Any,
        aerosol: Any,
        ts: datetime,
        region: str,
        city: str,
    ) -> SatelliteEvent | None:
        values = _required_floats(
            {"cloud_cover": cloud_cover, "aerosol_optical_depth": aerosol},
            ("cloud_cover", "aerosol_optical_depth"),
        )
        if values is None:
            self._skip(_REASON_MISSING_FIELD, region, city, "satellite")
            return None
        try:
            return SatelliteEvent(
                ts=ts,
                region=region,
                cloud_cover_pct=values["cloud_cover"],
                # E-3: a configured monthly reference, not a measurement.
                vegetation_index=self._monthly_vegetation[region][ts.month - 1],
                aerosol_index=values["aerosol_optical_depth"],
            )
        except ValidationError:
            self._skip(_REASON_SCHEMA, region, city, "satellite")
            return None

    def fetch_history(
        self, *, past_days: int = 1, not_after: datetime | None = None
    ) -> list[WeatherEvent | SatelliteEvent]:
        """Fetch the recent hourly series per city, for the live demo backfill.

        Deliberately not part of the EventSource Protocol, which describes one
        tick. The demo needs a series of windows rather than a single instant,
        and both endpoints serve hourly arrays covering recent days, so the demo
        can show genuine history instead of a manufactured one (ADR-0007).

        Future hours are excluded. The request necessarily spans a forecast day,
        and publishing a forecast value as a reading would be exactly the
        fabrication the rest of this adapter refuses.

        The no-fabrication rule applies per hourly slot: a null anywhere in an
        hourly array means no event for that slot and that city, counted and
        logged, never interpolated from its neighbours.
        """
        cutoff = not_after if not_after is not None else datetime.now(UTC)
        extra = {"past_days": past_days, "forecast_days": 1}
        events: list[WeatherEvent | SatelliteEvent] = []

        with self._open_client() as client:
            for region in self._regions:
                for city in self._locations[region]:
                    weather_payload = self._get(
                        client,
                        self._weather_url,
                        self._weather_params(city, "hourly", extra),
                        region,
                        city.name,
                        "weather",
                    )
                    air_payload = self._get(
                        client,
                        self._air_quality_url,
                        self._air_quality_params(city, "hourly", extra),
                        region,
                        city.name,
                        "satellite",
                    )
                    events.extend(
                        self._history_for_city(
                            weather_payload, air_payload, region, city.name, cutoff
                        )
                    )

        self._log.event(
            "source_history_complete",
            regions=len(self._regions),
            past_days=past_days,
            emitted=len(events),
            unavailable=self._missing,
        )
        return events

    def _history_for_city(
        self,
        weather_payload: dict[str, Any] | None,
        air_payload: dict[str, Any] | None,
        region: str,
        city: str,
        cutoff: datetime,
    ) -> list[WeatherEvent | SatelliteEvent]:
        """Walk the hourly arrays, emitting only the slots that are fully present."""
        events: list[WeatherEvent | SatelliteEvent] = []
        weather_hourly = self._hourly_block(weather_payload, region, city, "weather")
        if weather_hourly is None:
            return events

        aerosol_by_time: dict[str, float] = {}
        air_hourly = self._hourly_block(air_payload, region, city, "satellite")
        if air_hourly is not None:
            times = air_hourly.get("time") or []
            values = air_hourly.get("aerosol_optical_depth") or []
            for raw_time, value in zip(times, values, strict=False):
                if isinstance(raw_time, str) and isinstance(value, int | float):
                    aerosol_by_time[raw_time] = float(value)

        times = weather_hourly.get("time") or []
        for index, raw_time in enumerate(times):
            if not isinstance(raw_time, str):
                continue
            try:
                ts = _parse_utc(raw_time)
            except ValueError:
                self._skip(_REASON_MALFORMED, region, city, "weather", field="time")
                continue
            if ts > cutoff:
                # A forecast hour, not a reading. Silently out of scope rather
                # than a gap: it was never claimed to have happened.
                continue

            slot = _hourly_slot(weather_hourly, index, _WEATHER_CURRENT)
            if slot is None:
                self._skip(_REASON_MISSING_FIELD, region, city, "weather", hour=raw_time)
                continue

            weather = self._build_weather(slot, ts, region, city)
            if weather is not None:
                events.append(weather)

            aerosol = aerosol_by_time.get(raw_time)
            if aerosol is None:
                self._skip(_REASON_MISSING_FIELD, region, city, "satellite", hour=raw_time)
                continue
            satellite = self._build_satellite(
                cloud_cover=slot.get("cloud_cover"),
                aerosol=aerosol,
                ts=ts,
                region=region,
                city=city,
            )
            if satellite is not None:
                events.append(satellite)
        return events

    def _hourly_block(
        self, payload: dict[str, Any] | None, region: str, city: str, stream: str
    ) -> dict[str, Any] | None:
        if payload is None:
            return None
        if payload.get("utc_offset_seconds") != 0:
            self._skip(_REASON_OFFSET, region, city, stream)
            return None
        block = payload.get("hourly")
        if not isinstance(block, dict):
            self._skip(_REASON_MISSING_FIELD, region, city, stream, field="hourly")
            return None
        return block


def _parse_utc(raw: str) -> datetime:
    """Parse an Open-Meteo timestamp and attach UTC explicitly.

    The API returns a naive ISO string even when asked for ``timezone=UTC``, and
    the entity models reject naive datetimes (E-2, E-3). Callers confirm the
    response's ``utc_offset_seconds`` is zero before calling this, so attaching
    UTC states what the response actually said rather than assuming it.
    """
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC)
    return parsed.replace(tzinfo=UTC)


def _required_floats(block: Mapping[str, Any], names: Sequence[str]) -> dict[str, float] | None:
    """Return the named values as floats, or None if any is absent or null.

    Booleans are rejected despite being int subclasses: a bool here means the
    payload is not what it claims, not a reading of zero or one.
    """
    values: dict[str, float] = {}
    for name in names:
        value = block.get(name)
        if value is None or isinstance(value, bool) or not isinstance(value, int | float):
            return None
        values[name] = float(value)
    return values


def _hourly_slot(
    hourly: Mapping[str, Any], index: int, names: Sequence[str]
) -> dict[str, Any] | None:
    """Pull one hour's values out of the parallel arrays, or None if any is null."""
    slot: dict[str, Any] = {}
    for name in names:
        series = hourly.get(name)
        if not isinstance(series, list) or index >= len(series):
            return None
        value = series[index]
        if value is None:
            return None
        slot[name] = value
    return slot
