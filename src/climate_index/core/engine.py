"""Windowing engine: validated events to aggregate records (UC-3).

Groups a batch of validated events by their natural key ``(region,
window_start, window_end)`` using event-time bucketing, then for each group
computes the component metrics, the impact index, and the confidence grade, and
emits one :class:`ClimateIndexRecord` per region per window.

Pure and deterministic: the same events in any order produce the same records
(sorted by region then window start), so tests pin exact outputs and replays
reproduce identical natural keys. No transport or store dependency (INV-4).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from climate_index.config import Settings, get_settings
from climate_index.core.confidence import grade_confidence
from climate_index.core.features import (
    dryness_index,
    impact_index,
    pollution_index,
    temperature_anomaly,
)
from climate_index.core.models import ClimateIndexRecord, SatelliteEvent, WeatherEvent
from climate_index.core.windowing import assign_window

_WindowKey = tuple[str, datetime, datetime]


class _Bucket:
    """The weather and satellite events collected for one window key."""

    def __init__(self) -> None:
        self.weather: list[WeatherEvent] = []
        self.satellite: list[SatelliteEvent] = []


def compute_records(
    events: Iterable[WeatherEvent | SatelliteEvent],
    settings: Settings | None = None,
) -> list[ClimateIndexRecord]:
    """Compute one aggregate record per region per closed window.

    ``events`` are validated events (the output of the validation gate). Records
    are returned ordered by ``(region, window_start)`` for deterministic output.
    """
    settings = settings if settings is not None else get_settings()
    window_minutes = settings.window_minutes

    buckets: dict[_WindowKey, _Bucket] = {}
    for event in events:
        window_start, window_end = assign_window(event.ts, window_minutes)
        key: _WindowKey = (event.region, window_start, window_end)
        bucket = buckets.setdefault(key, _Bucket())
        if isinstance(event, WeatherEvent):
            bucket.weather.append(event)
        else:
            bucket.satellite.append(event)

    records: list[ClimateIndexRecord] = []
    for key, bucket in sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1])):
        region, window_start, window_end = key
        # The window's own month, not each event's, so every event in a window is
        # measured against one normal (E-7).
        anomaly = temperature_anomaly(bucket.weather, region, window_start.month, settings)
        dryness = dryness_index(bucket.weather, bucket.satellite, settings)
        pollution = pollution_index(bucket.satellite, settings)
        records.append(
            ClimateIndexRecord(
                region=region,
                window_start=window_start,
                window_end=window_end,
                impact_index=impact_index(anomaly, dryness, pollution, settings),
                temperature_anomaly=anomaly,
                dryness_index=dryness,
                pollution_index=pollution,
                confidence=grade_confidence(len(bucket.weather), len(bucket.satellite), settings),
            )
        )
    return records
