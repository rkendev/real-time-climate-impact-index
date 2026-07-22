"""Read-only Climate Impact Index dashboard (UC-5, FR-8, FR-9, NFR-P3, INV-2).

A Streamlit page with a region selector, a time series of the impact index over
recent windows, the current value, its verbal label, and its confidence grade,
wrapped in enough plain language that a first-time viewer can read it unaided:
what the index is and which way it points, which source the feed is actually
coming from, when the served snapshot last moved and how often it refreshes,
what each confidence tier means, and where the label bands fall.

Every one of those definitions is read from
:class:`~climate_index.config.Settings`, which holds them as the single authority
(INV-1). The page states nothing of its own: the band cutoffs come from
``label_thresholds``, the tier glosses from ``confidence_tier_glosses``, the strip
colours from ``confidence_tier_colors``, the feed notice is whichever of the two
configured notices matches ``source_backend``, and each window's grade is the
value the pipeline stored on that row. Nothing here sets or adjusts a grade.

Provenance claims are made only where they are true. The feed notice names the
source actually configured, and the provider attribution appears only when the
real source is live, because attributing simulated numbers to a data provider
would assert a provenance the page does not have (UC-5, ADR-0007).

Window times are written as UTC clock labels on the server (``as_utc`` is the one
place the page handles zones, and ``window_axis_time_format`` holds the pattern),
and each chart's axis is pinned to that ordered label sequence. A datetime handed
to the browser would be redrawn in the viewer's own zone, so an axis titled UTC
would quietly show local time; formatting here keeps the axis and the freshness
line quoting the same clock.

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
from datetime import UTC, datetime
from typing import Any

# Altair is Streamlit's own charting library, installed by the streamlit pin, so
# nothing new is added to requirements.txt. The page reaches for it directly
# because the built-in chart calls cannot express what this axis needs: they hand
# window datetimes to the browser, which localizes a temporal axis whatever the
# axis is titled, and they offer no way to pin a category axis to an explicit
# order or to map the confidence tiers to chosen colours while keeping a legend.
import altair as alt
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


def is_real_feed(settings: Settings) -> bool:
    """Whether the real source is the one configured.

    Anything unrecognised reads as not-real, because understating what the feed
    is can only disappoint a viewer, while overstating it misleads one.
    """
    return settings.source_backend == "real"


def feed_notice(settings: Settings) -> str:
    """The notice matching the source actually configured (UC-5, ADR-0007).

    Selecting, not composing: both notices are written in config, which holds
    them as their single authority, and this picks the one whose backend is in
    force. The page can therefore never claim a provenance the pipeline is not
    running, in either direction.
    """
    return settings.real_feed_notice if is_real_feed(settings) else settings.simulated_feed_notice


def attribution_line(settings: Settings) -> str:
    """The provider attribution, or an empty string when no provider data is used.

    Attribution belongs to data actually present. Under the simulated source no
    provider reading has been fetched, so naming one would assert a provenance
    the page does not have, which is the exact failure this whole change exists
    to remove. It appears only when the real source is live.
    """
    return settings.source_attribution if is_real_feed(settings) else ""


def as_utc(moment: datetime) -> datetime:
    """Move a stored instant into UTC, the one place this page handles zones.

    Every time the page shows comes through here, so the freshness line and the
    chart axis cannot disagree about which clock they are quoting. The reader
    already returns aware UTC datetimes; a naive value is read as UTC rather than
    as the server's local time, which is how the stores write them.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def freshness_line(view: RegionView, settings: Settings) -> str:
    """State when the served snapshot last moved and how often it refreshes."""
    if not view.window_starts:
        return ""
    newest = as_utc(view.window_starts[-1])
    return (
        f"Newest window starts {newest.strftime('%Y-%m-%d %H:%M')} UTC. "
        f"Each window covers {settings.window_minutes} minutes, "
        f"and the snapshot refreshes every {settings.demo_refresh_interval}."
    )


def utc_axis_labels(window_starts: Sequence[datetime], settings: Settings) -> tuple[str, ...]:
    """Write each window start as a UTC clock label, in the series' own order.

    The label is formatted here, on the server, from the UTC instant
    :func:`as_utc` returns, so the browser is handed a category rather than a
    datetime it would localize: the axis then reads the same clock the freshness
    line quotes. The order returned is the order given, which is the order the
    store read the rows in (oldest to newest, by window start). Callers pin the
    axis to this sequence and never re-derive the order from the labels: a series
    that crosses midnight runs 23:30 then 00:00, which sorts the wrong way round
    as text.
    """
    return tuple(
        as_utc(start).strftime(settings.window_axis_time_format) for start in window_starts
    )


def series_rows(view: RegionView, settings: Settings) -> list[dict[str, Any]]:
    """Rows for the index chart: the UTC window label against the stored index."""
    labels = utc_axis_labels(view.window_starts, settings)
    return [
        {WINDOW_COLUMN: label, settings.index_axis_label: value}
        for label, value in zip(labels, view.impact_series, strict=True)
    ]


def confidence_rows(view: RegionView, settings: Settings) -> list[dict[str, Any]]:
    """Rows for the confidence strip: one bar per window, coloured by grade.

    The colour field carries the grade the pipeline stored for that window, so
    the strip shows what was computed rather than anything decided here.
    """
    labels = utc_axis_labels(view.window_starts, settings)
    return [
        {WINDOW_COLUMN: label, WINDOW_COUNT_COLUMN: 1, CONFIDENCE_COLUMN: grade}
        for label, grade in zip(labels, view.confidence_series, strict=True)
    ]


def index_chart(view: RegionView, settings: Settings) -> alt.Chart:
    """The index series over the UTC window labels, oldest to newest.

    The axis is a category axis whose domain is the label sequence itself, so the
    points stay in the order the store read them however the labels would sort as
    text, and no browser localizes anything.
    """
    labels = utc_axis_labels(view.window_starts, settings)
    return (
        alt.Chart(alt.Data(values=series_rows(view, settings)))
        .mark_line(point=True)
        .encode(
            x=alt.X(field=WINDOW_COLUMN, type="ordinal", title=WINDOW_COLUMN, sort=list(labels)),
            y=alt.Y(
                field=settings.index_axis_label,
                type="quantitative",
                title=settings.index_axis_label,
            ),
            tooltip=[
                alt.Tooltip(field=WINDOW_COLUMN, type="ordinal"),
                alt.Tooltip(field=settings.index_axis_label, type="quantitative"),
            ],
        )
    )


def confidence_chart(view: RegionView, settings: Settings) -> alt.Chart:
    """One bar per window on the same UTC axis, coloured by the stored grade.

    The colours are read from ``confidence_tier_colors``, which holds them as the
    single authority beside the glosses (INV-1), and the scale is pinned to the
    configured tiers rather than assigned in the order grades happen to appear.
    A tier therefore always draws in its own colour whatever the window set
    contains, and the legend still names every tier by grade.
    """
    labels = utc_axis_labels(view.window_starts, settings)
    tier_colors = settings.confidence_tier_colors
    return (
        alt.Chart(alt.Data(values=confidence_rows(view, settings)))
        .mark_bar()
        .encode(
            x=alt.X(field=WINDOW_COLUMN, type="ordinal", title=WINDOW_COLUMN, sort=list(labels)),
            y=alt.Y(field=WINDOW_COUNT_COLUMN, type="quantitative", title=CONFIDENCE_COLUMN),
            color=alt.Color(
                field=CONFIDENCE_COLUMN,
                type="nominal",
                title=CONFIDENCE_COLUMN,
                scale=alt.Scale(domain=list(tier_colors), range=list(tier_colors.values())),
                # Below the strip, where the built-in chart used to put it.
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip(field=WINDOW_COLUMN, type="ordinal"),
                alt.Tooltip(field=CONFIDENCE_COLUMN, type="nominal"),
            ],
        )
    )


def render(store: ReadOnlyAggregateStore, settings: Settings) -> None:
    """Render the read-only page for the selected region."""
    st.title("Real-Time Climate Impact Index")
    st.write(settings.index_summary)
    st.caption(feed_notice(settings))

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
    st.altair_chart(index_chart(view, settings), width="stretch")
    st.caption(f"One point per {settings.window_minutes} minute window, oldest to newest.")
    # Sized by its content: constraining the height here leaves the axis and the
    # legend nothing to sit in and the bars stop being drawn at all.
    st.altair_chart(confidence_chart(view, settings), width="stretch")
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
        attribution = attribution_line(settings)
        if attribution:
            st.caption(attribution)
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
