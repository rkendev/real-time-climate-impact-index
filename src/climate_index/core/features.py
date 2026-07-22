"""Derived feature and index computation (UC-3, FR-4, FR-5).

Per region per event-time window, these pure functions turn the window's
validated events into the three component metrics of E-7 and combine them into
the 0..100 impact index. They import no transport or store client and hold no
structural constants of their own: the baselines, weights, and formula
saturation points are the sole authority of :mod:`climate_index.config` (INV-4,
AT-10). The verbal-label mapping (FR-9) is display formatting, not index
computation, and lives apart in :mod:`climate_index.labels` so the read-only
dashboard can use it without importing this compute path (INV-2, AT-6).

Chosen bounded forms (E-7 leaves the exact form to the implementation):

* ``temperature_anomaly`` = mean ``temperature_c`` minus the per-region normal
  for the window's calendar month. Raw degrees Celsius, may be negative; it is
  the one component metric the spec does not bound.
* ``dryness_index`` in ``[0, 1]``, rising as it gets drier. The mean of up to two
  sub-scores: a rainfall sub-score ``clamp(1 - mean_rainfall / saturation, 0, 1)``
  (weather) and a vegetation sub-score ``(1 - mean_vegetation_index) / 2``
  (satellite). When only one source is present the record still computes from
  that sub-score alone (single-type imputation, NFR-R4); when neither is present
  it imputes to 0.0.
* ``pollution_index`` in ``[0, 1]``, rising with haze and cloud. The mean of an
  aerosol sub-score ``clamp(mean_aerosol_index / saturation, 0, 1)`` and a cloud
  sub-score ``mean_cloud_cover_pct / 100`` (both satellite). Absent satellite it
  imputes to 0.0.
* ``impact_index`` = ``100 * weighted_sum / total_weight`` where the temperature
  component is normalized to ``[0, 1]`` by ``clamp(anomaly / scale, 0, 1)`` (a
  cooler-than-baseline window contributes no warming stress). Dividing by the
  weight sum keeps the result in ``[0, 100]`` for any weight configuration.

These forms are candidates to record in spec E-7; see the implementation report.
"""

from __future__ import annotations

from collections.abc import Sequence

from climate_index.config import Settings, get_settings
from climate_index.core.models import SatelliteEvent, WeatherEvent


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def temperature_anomaly(
    weather: Sequence[WeatherEvent],
    region: str,
    month: int,
    settings: Settings | None = None,
) -> float:
    """Mean ``temperature_c`` minus the region's normal for ``month`` (E-7, FR-4).

    ``month`` is the calendar month of the window, 1 for January through 12 for
    December, taken by the caller from the window start so that every event in a
    window is measured against the same normal whatever its own timestamp.
    Measuring against a monthly normal rather than one annual scalar is what
    keeps the anomaly meaningful in both configured sources: a July reading
    compared to an annual average would report a large positive anomaly every
    summer and a large negative one every winter, in any region with seasons.

    An empty weather set imputes to 0.0 (no anomaly signal from this window).
    """
    settings = settings if settings is not None else get_settings()
    if not weather:
        return 0.0
    baseline = settings.region_monthly_baselines[region][month - 1]
    return _mean([event.temperature_c for event in weather]) - baseline


def dryness_index(
    weather: Sequence[WeatherEvent],
    satellite: Sequence[SatelliteEvent],
    settings: Settings | None = None,
) -> float:
    """Bounded ``[0, 1]`` dryness rising with low rainfall and low vegetation."""
    settings = settings if settings is not None else get_settings()
    sub_scores: list[float] = []
    if weather:
        mean_rainfall = _mean([event.rainfall_mm for event in weather])
        rain_ratio = mean_rainfall / settings.dryness_rainfall_saturation_mm
        sub_scores.append(_clamp(1.0 - rain_ratio, 0.0, 1.0))
    if satellite:
        mean_vegetation = _mean([event.vegetation_index for event in satellite])
        sub_scores.append((1.0 - mean_vegetation) / 2.0)
    if not sub_scores:
        return 0.0
    return _mean(sub_scores)


def pollution_index(
    satellite: Sequence[SatelliteEvent],
    settings: Settings | None = None,
) -> float:
    """Bounded ``[0, 1]`` pollution rising with aerosol and cloud cover."""
    settings = settings if settings is not None else get_settings()
    if not satellite:
        return 0.0
    mean_aerosol = _mean([event.aerosol_index for event in satellite])
    mean_cloud = _mean([event.cloud_cover_pct for event in satellite])
    aerosol_sub = _clamp(mean_aerosol / settings.pollution_aerosol_saturation, 0.0, 1.0)
    cloud_sub = mean_cloud / 100.0
    return _mean([aerosol_sub, cloud_sub])


def impact_index(
    anomaly: float,
    dryness: float,
    pollution: float,
    settings: Settings | None = None,
) -> float:
    """Weighted, normalized combination of the three components in ``[0, 100]``."""
    settings = settings if settings is not None else get_settings()
    weights = settings.index_weights
    temperature_component = _clamp(anomaly / settings.temperature_anomaly_scale_c, 0.0, 1.0)

    weighted_sum = (
        weights["temperature_anomaly"] * temperature_component
        + weights["dryness_index"] * dryness
        + weights["pollution_index"] * pollution
    )
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("index_weights must sum to a positive value")

    return _clamp(100.0 * weighted_sum / total_weight, 0.0, 100.0)
