"""Verbal-label mapping, a display-safe module (FR-9, UC-5, INV-2).

Maps a stored ``impact_index`` to the verbal band ``"low"``/``"medium"``/
``"high"`` by the fixed, configured thresholds (E-7, FR-9). This is display
formatting, not index computation: it derives no metric and reads no event, so
the read-only dashboard can import it without pulling in the feature or index
math (``core.features``, ``core.engine``) or any store writer. Keeping it here,
apart from the compute core, is what lets the dashboard stay strictly read-only
(INV-2, AT-6). The band boundaries are the sole authority of
:mod:`climate_index.config`; no threshold literal appears here.
"""

from __future__ import annotations

from climate_index.config import Settings, get_settings


def verbal_label(index: float, settings: Settings | None = None) -> str:
    """Map an impact index to ``"low"``, ``"medium"``, or ``"high"`` (FR-9)."""
    settings = settings if settings is not None else get_settings()
    thresholds = settings.label_thresholds
    if index <= thresholds["low_max"]:
        return "low"
    if index <= thresholds["medium_max"]:
        return "medium"
    return "high"
