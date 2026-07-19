"""Read-only Climate Impact Index dashboard (UC-5, FR-8, FR-9, NFR-P3, INV-2).

A Streamlit page with a region selector, a time series of the impact index over
recent windows, the current value, its verbal label, and its confidence grade.
It reads the aggregate store only through
:class:`~climate_index.adapters.duckdb.reader.DuckDBReadOnlyAggregateStore`, a
read-only connection, and it imports no index or feature computation and no store
writer. The verbal label comes from the display-safe
:func:`~climate_index.labels.verbal_label`, not from the compute core, so the
page performs no index computation and issues no writes (INV-2, FR-8, AT-6).

Run with ``make ui`` (``streamlit run app/dashboard.py``). Under Streamlit the
script runs as ``__main__`` and ``main()`` fires; a plain import is
side-effect-free, so :func:`build_region_view` is importable for tests without
launching the UI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import streamlit as st

from climate_index.adapters.duckdb.reader import DuckDBReadOnlyAggregateStore
from climate_index.config import Settings, get_settings
from climate_index.labels import verbal_label


@dataclass(frozen=True)
class RegionView:
    """The display model for one region's series, built read-only from the store."""

    region: str
    window_starts: tuple[str, ...]
    impact_series: tuple[float, ...]
    current_value: float | None
    label: str | None
    confidence: str | None


def build_region_view(rows: Sequence[Mapping[str, Any]], region: str) -> RegionView:
    """Build the display model from aggregate rows (ordered by window start).

    The current value is the most recent window's index; its verbal label is
    derived with :func:`verbal_label` (display formatting, FR-9), and the
    confidence grade is read straight from the stored row. No index is computed.
    """
    if not rows:
        return RegionView(region, (), (), None, None, None)
    window_starts = tuple(str(row["window_start"].isoformat()) for row in rows)
    impact_series = tuple(float(row["impact_index"]) for row in rows)
    current_value = impact_series[-1]
    return RegionView(
        region=region,
        window_starts=window_starts,
        impact_series=impact_series,
        current_value=current_value,
        label=verbal_label(current_value),
        confidence=str(rows[-1]["confidence"]),
    )


def render(store: DuckDBReadOnlyAggregateStore, settings: Settings) -> None:
    """Render the read-only page for the selected region."""
    st.title("Real-Time Climate Impact Index")
    st.caption("Read-only view of the aggregate store (one row per region per window).")

    regions = list(settings.region_list)
    region = st.selectbox("Region", regions)

    view = build_region_view(store.read_region_series(region), region)
    if view.current_value is None:
        st.info(f"No windows for {region} yet. Run `make run_processor` to seed the store.")
        return

    current, label, confidence = st.columns(3)
    current.metric("Current impact index", f"{view.current_value:.1f}")
    label.metric("Label", view.label)
    confidence.metric("Confidence", view.confidence)

    st.subheader("Impact index over recent windows")
    st.line_chart({"impact_index": list(view.impact_series)})


def main() -> None:
    """Open the read-only store from config and render (the ``make ui`` entry)."""
    settings = get_settings()
    if not settings.aggregate_store_path.exists():
        st.title("Real-Time Climate Impact Index")
        st.info("No aggregate store found. Run `make run_processor` to seed it, then reload.")
        return

    store = DuckDBReadOnlyAggregateStore(settings.aggregate_store_path)
    try:
        render(store, settings)
    finally:
        store.close()


if __name__ == "__main__":
    main()
