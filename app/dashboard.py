"""Read-only Climate Impact Index dashboard (UC-5, FR-8, FR-9, NFR-P3, INV-2).

A Streamlit page with a region selector, a time series of the impact index over
recent windows, the current value, its verbal label, and its confidence grade,
wrapped in enough plain language that a first-time viewer can read it unaided:
what the index is and which way it points, that the feed is simulated, when the
served snapshot last moved and how often it refreshes, what each confidence tier
means, and where the label bands fall.

Every one of those definitions is read from
:class:`~climate_index.config.Settings`, which holds them as the single authority
(INV-1). The page states nothing of its own: the band cutoffs come from
``label_thresholds``, the tier glosses from ``confidence_tier_glosses``, and each
window's grade is the value the pipeline stored on that row. Nothing here sets or
adjusts a grade.

It reads the aggregate store only through a read-only store built by
:func:`~climate_index.store_factory.build_readonly_aggregate_store`, which selects
the DuckDB reader locally or the DynamoDB serving reader on AWS by config; both
expose only reads. The page imports no index or feature computation and no store
writer, and it is typed against
:class:`~climate_index.interfaces.store.ReadOnlyAggregateStore`, so it holds no
write capability. The verbal label comes from the display-safe
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
from datetime import datetime
from typing import Any

import streamlit as st

from climate_index.config import Settings, get_settings
from climate_index.interfaces.store import ReadOnlyAggregateStore
from climate_index.labels import verbal_label
from climate_index.store_factory import build_readonly_aggregate_store

# Column captions for the chart frames. Axis wording that is a definition (the
# index and its range) comes from config; these name the frame's own columns.
WINDOW_COLUMN = "Window start (UTC)"
CONFIDENCE_COLUMN = "Confidence"
WINDOW_COUNT_COLUMN = "Windows"


@dataclass(frozen=True)
class RegionView:
    """The display model for one region's series, built read-only from the store."""

    region: str
    window_starts: tuple[datetime, ...]
    window_ends: tuple[datetime, ...]
    impact_series: tuple[float, ...]
    confidence_series: tuple[str, ...]
    current_value: float | None
    label: str | None
    confidence: str | None


def build_region_view(rows: Sequence[Mapping[str, Any]], region: str) -> RegionView:
    """Build the display model from aggregate rows (ordered by window start).

    The current value is the most recent window's index; its verbal label is
    derived with :func:`verbal_label` (display formatting, FR-9), and the
    confidence grade of every window is read straight from its stored row. No
    index is computed and no grade is assigned here.
    """
    if not rows:
        return RegionView(region, (), (), (), (), None, None, None)
    window_starts = tuple(row["window_start"] for row in rows)
    window_ends = tuple(row["window_end"] for row in rows)
    impact_series = tuple(float(row["impact_index"]) for row in rows)
    confidence_series = tuple(str(row["confidence"]) for row in rows)
    current_value = impact_series[-1]
    return RegionView(
        region=region,
        window_starts=window_starts,
        window_ends=window_ends,
        impact_series=impact_series,
        confidence_series=confidence_series,
        current_value=current_value,
        label=verbal_label(current_value),
        confidence=confidence_series[-1],
    )


def band_legend_lines(settings: Settings) -> tuple[str, ...]:
    """Spell out the verbal-label bands from the configured cutoffs (FR-9).

    The cutoffs are read from ``label_thresholds``, the same values
    :func:`verbal_label` maps with, so the legend cannot drift from the label.
    """
    thresholds = settings.label_thresholds
    low_max = thresholds["low_max"]
    medium_max = thresholds["medium_max"]
    return (
        f"low: index at or below {low_max:g}",
        f"medium: index above {low_max:g} and at or below {medium_max:g}",
        f"high: index above {medium_max:g}",
    )


def tier_legend_lines(settings: Settings) -> tuple[str, ...]:
    """Name each confidence tier with what drives it (NFR-DQ2), from config."""
    return tuple(f"{tier}: {gloss}" for tier, gloss in settings.confidence_tier_glosses.items())


def tier_gloss(confidence: str | None, settings: Settings) -> str:
    """The one-phrase gloss for a stored grade, or an empty string if unknown."""
    if confidence is None:
        return ""
    return settings.confidence_tier_glosses.get(confidence, "")


def freshness_line(view: RegionView, settings: Settings) -> str:
    """State when the served snapshot last moved and how often it refreshes."""
    if not view.window_starts:
        return ""
    newest = view.window_starts[-1]
    return (
        f"Newest window starts {newest.strftime('%Y-%m-%d %H:%M')} UTC. "
        f"Each window covers {settings.window_minutes} minutes, "
        f"and the snapshot refreshes every {settings.demo_refresh_interval}."
    )


def series_frame(view: RegionView, settings: Settings) -> dict[str, list[Any]]:
    """Columns for the index chart: real window times against the stored index."""
    return {
        WINDOW_COLUMN: list(view.window_starts),
        settings.index_axis_label: list(view.impact_series),
    }


def confidence_frame(view: RegionView) -> dict[str, list[Any]]:
    """Columns for the confidence strip: one bar per window, coloured by grade.

    The colour column carries the grade the pipeline stored for that window, so
    the strip shows what was computed rather than anything decided here.
    """
    return {
        WINDOW_COLUMN: list(view.window_starts),
        WINDOW_COUNT_COLUMN: [1] * len(view.window_starts),
        CONFIDENCE_COLUMN: list(view.confidence_series),
    }


def render(store: ReadOnlyAggregateStore, settings: Settings) -> None:
    """Render the read-only page for the selected region."""
    st.title("Real-Time Climate Impact Index")
    st.write(settings.index_summary)
    st.caption(settings.simulated_feed_notice)

    regions = list(settings.region_list)
    region = st.selectbox("Region", regions)

    view = build_region_view(store.read_region_series(region), region)
    if view.current_value is None:
        st.info(f"No windows for {region} yet. Run `make run_processor` to seed the store.")
        return

    st.caption(freshness_line(view, settings))

    current, label, confidence = st.columns(3)
    current.metric("Current impact index", f"{view.current_value:.1f}")
    label.metric("Label", view.label)
    confidence.metric("Confidence", view.confidence)
    confidence.caption(tier_gloss(view.confidence, settings))

    st.subheader("Impact index over recent windows")
    st.line_chart(
        series_frame(view, settings),
        x=WINDOW_COLUMN,
        y=settings.index_axis_label,
        x_label=WINDOW_COLUMN,
        y_label=settings.index_axis_label,
    )
    st.caption(f"One point per {settings.window_minutes} minute window, oldest to newest.")
    st.bar_chart(
        confidence_frame(view),
        x=WINDOW_COLUMN,
        y=WINDOW_COUNT_COLUMN,
        color=CONFIDENCE_COLUMN,
        x_label=WINDOW_COLUMN,
        y_label=CONFIDENCE_COLUMN,
        height=140,
    )
    st.caption(
        "The strip carries the confidence grade the pipeline computed for each window "
        "from that window's input."
    )

    with st.expander("What the tiers and labels mean"):
        st.write("Confidence grades the evidence behind a window, not the index value:")
        for line in tier_legend_lines(settings):
            st.write(f"- {line}")
        st.write("The verbal label is a fixed mapping of the index:")
        for line in band_legend_lines(settings):
            st.write(f"- {line}")

    with st.expander("About / how it works"):
        st.write(settings.pipeline_summary)
        url = settings.source_repository_url
        st.markdown(f"Source code and documentation: [{url}]({url})")


def main() -> None:
    """Open the configured read-only store and render (the ``make ui`` entry).

    The store is chosen by config: the DuckDB reader locally, the DynamoDB serving
    reader on AWS. Only the local backend has a file to check for, so the
    seed-first hint is guarded to that backend; on AWS the reader queries the
    serving table directly. The close is guarded because not every reader holds a
    connection to close (the DynamoDB reader does not).
    """
    settings = get_settings()
    if settings.aggregate_backend == "duckdb" and not settings.aggregate_store_path.exists():
        st.title("Real-Time Climate Impact Index")
        st.info("No aggregate store found. Run `make run_processor` to seed it, then reload.")
        return

    store = build_readonly_aggregate_store(settings)
    try:
        render(store, settings)
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
