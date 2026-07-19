"""Provenance-graded confidence for an aggregate row (NFR-DQ2, NFR-R4).

The grade is a pure function of the window's input composition, not of the index
value. A single-type window is graded down rather than dropped (NFR-R4), so a
degraded reading is still published with an honest provenance label instead of a
gap. The sparsity threshold is a config constant (INV / no core magic numbers).

Precedence: sparsity dominates. A window below the minimum event count is
AMBIGUOUS whatever its composition, because too little input makes the
composition itself unreliable.
"""

from __future__ import annotations

from climate_index.config import Settings, get_settings
from climate_index.core.models import Confidence


def grade_confidence(
    weather_count: int,
    satellite_count: int,
    settings: Settings | None = None,
) -> Confidence:
    """Grade a window from its weather and satellite event counts.

    * AMBIGUOUS when the total event count is below ``sparsity_min_events``.
    * MEASURED when both stream types are present.
    * INFERRED when exactly one stream type is present (a component is imputed
      from a single type).
    """
    settings = settings if settings is not None else get_settings()
    total = weather_count + satellite_count

    if total < settings.sparsity_min_events:
        return Confidence.AMBIGUOUS
    if weather_count > 0 and satellite_count > 0:
        return Confidence.MEASURED
    return Confidence.INFERRED
