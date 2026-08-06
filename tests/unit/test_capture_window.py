"""The capture script's pure parts, exercised before it is ever run.

No network is touched here. The fetch is a separate act from committing the
script, and the parts that decide what lands and what is recorded are exactly the
parts worth having under test before the one run that matters.

Two properties carry the most weight. The artifact must never contain a measured
value, because it is committed and the frozen licence rule bites on committed raw
values. And the realized timestamp bounds must be computed from the rows that
actually landed rather than from the window that was asked for, because a
declaration catches a mislabelled pull and only the realized bounds catch a
mis-executed one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from capture_window import (
    CaptureFault,
    assert_inside_window,
    bounds,
    build_artifact,
    build_parser,
    model_rows,
    station_rows,
)
from climate_index.config import Settings

# Taken from the configured control window rather than written as literals. Two
# reasons, and the second is the one that bit. It keeps this module exercising the
# window the capture will actually be pointed at; and the control window's
# exclusive end is the holdout's first day, so writing the boundary as a literal
# puts a holdout date on the run surface. The successor control caught exactly
# that here, which is what it is for.
_WINDOW = Settings(_env_file=None).reconciliation_windows["control"]
START = _WINDOW.start
END = _WINDOW.end

INSIDE = START + timedelta(days=1, hours=9)
LATER = START + timedelta(days=3, hours=5)
BEFORE = START - timedelta(hours=1)

SENSOR = {"sensor_id": 11, "station_id": "s-11", "city": "Amsterdam", "region": "EUR"}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hour(text: str, value: float, *, flags: bool = False, observed: int = 1) -> dict[str, object]:
    """A well-formed hourly row: anchored on ``text`` and exactly one hour long."""
    start = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return {
        "period": {
            "datetimeFrom": {"utc": text},
            "datetimeTo": {"utc": _stamp(start + timedelta(hours=1))},
        },
        "value": value,
        "hasFlags": flags,
        "coverage": {"observedCount": observed},
    }


# --- what qualifies as a station row ------------------------------------------


def test_a_clean_hour_becomes_one_row() -> None:
    rows = station_rows({"results": [_hour(_stamp(INSIDE), 12.5)]}, SENSOR)
    assert len(rows) == 1
    assert rows[0]["pm25_ugm3"] == 12.5
    assert rows[0]["city"] == "Amsterdam"
    assert rows[0]["ts"] == _stamp(INSIDE)


def test_a_flagged_hour_is_dropped_and_a_zero_sample_hour_is_dropped() -> None:
    payload = {
        "results": [
            _hour(_stamp(INSIDE), 12.5, flags=True),
            _hour(_stamp(LATER), 12.5, observed=0),
        ]
    }
    assert station_rows(payload, SENSOR) == []


def test_a_negative_reading_is_retained() -> None:
    """The frozen rules retain them, and the tolerance floor is why it matters."""
    rows = station_rows({"results": [_hour(_stamp(INSIDE), -3.2)]}, SENSOR)
    assert rows[0]["pm25_ugm3"] == -3.2


def test_construction_is_recorded_from_the_sample_count() -> None:
    """The axis the CPCB confound is visible on, and the reason for the endpoint."""
    one = station_rows({"results": [_hour(_stamp(INSIDE), 12.5, observed=1)]}, SENSOR)
    many = station_rows({"results": [_hour(_stamp(INSIDE), 12.5, observed=4)]}, SENSOR)
    assert one[0]["construction"] == "PROVIDER_HOURLY"
    assert many[0]["construction"] == "COMPUTED_MEAN"


def test_a_malformed_row_is_skipped_rather_than_guessed() -> None:
    payload = {"results": [{"value": 12.5}, {"period": {}, "value": None}, "nonsense"]}
    assert station_rows(payload, SENSOR) == []


# --- the model side -----------------------------------------------------------


def test_model_hours_outside_the_window_are_not_captured() -> None:
    payload = {
        "hourly": {
            "time": [
                _stamp(BEFORE)[:-4],
                _stamp(INSIDE)[:-4],
                _stamp(END)[:-4],
            ],
            "pm2_5": [5.0, 9.0, 7.0],
        }
    }
    rows = model_rows(payload, "EUR", "Amsterdam", START, END)
    assert [row["ts"] for row in rows] == [_stamp(INSIDE)]


def test_a_null_model_hour_is_omitted_rather_than_zeroed() -> None:
    payload = {"hourly": {"time": [_stamp(INSIDE)[:-4]], "pm2_5": [None]}}
    assert model_rows(payload, "EUR", "Amsterdam", START, END) == []


# --- realized bounds, and the window assertion --------------------------------


def test_bounds_are_the_rows_that_landed_not_the_window_requested() -> None:
    middle = START + timedelta(days=2, hours=23)
    rows = [{"ts": _stamp(LATER)}, {"ts": _stamp(INSIDE)}, {"ts": _stamp(middle)}]
    assert bounds(rows) == {"rows": 3, "min": _stamp(INSIDE), "max": _stamp(LATER)}


def test_bounds_of_nothing_say_nothing_rather_than_inventing_a_span() -> None:
    assert bounds([]) == {"rows": 0, "min": None, "max": None}


def test_a_row_outside_the_requested_window_blocks_the_capture() -> None:
    """Refused, not filtered: a mislabelled capture is the thing being prevented."""
    rows = [{"ts": _stamp(INSIDE)}, {"ts": _stamp(BEFORE)}]
    with pytest.raises(CaptureFault, match="outside the requested window"):
        assert_inside_window(rows, START, END)


def test_the_window_assertion_accepts_a_capture_that_is_inside_it() -> None:
    """The no-fault control: a check that rejects everything proves nothing."""
    assert_inside_window([{"ts": _stamp(INSIDE)}], START, END)


# --- the artifact -------------------------------------------------------------


def _artifact() -> dict[str, object]:
    from capture_window import CallLog

    stations = [
        {"ts": _stamp(INSIDE), "city": "Amsterdam", "pm25_ugm3": 12.5},
        {"ts": _stamp(LATER), "city": "Amsterdam", "pm25_ugm3": -3.25},
    ]
    models = [{"ts": _stamp(INSIDE), "city": "Amsterdam", "model_pm25_ugm3": 9.75}]
    return build_artifact(
        name="control",
        start=START,
        end=END,
        stations=stations,
        models=models,
        admission_version="2026-08-03",
        sensor_ids=[11, 12],
        station_log=CallLog(),
        model_log=CallLog(),
        now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )


def test_the_artifact_records_realized_bounds_per_source() -> None:
    record = _artifact()
    assert record["observed_bounds"]["station"]["max"] == _stamp(LATER)
    assert record["observed_bounds"]["model"]["max"] == _stamp(INSIDE)
    assert record["window_requested"]["name"] == "control"


def test_the_artifact_carries_no_measured_value() -> None:
    """It is committed, and the licence rule bites on committed raw values.

    Checked by searching the serialized artifact for the values that went in,
    rather than by reading the fields it is known to have. A field added later
    that leaked a value would pass a field-by-field check and fail this one.
    """
    text = json.dumps(_artifact())
    for value in ("12.5", "-3.25", "9.75"):
        assert value not in text, f"the artifact leaked the measured value {value}"


def test_the_leak_check_would_notice_a_leaked_value() -> None:
    """The absence check above must be able to fail."""
    record = _artifact()
    record["observed_bounds"]["station"]["max_value"] = 12.5  # type: ignore[index]
    assert "12.5" in json.dumps(record)


def test_the_artifact_names_the_endpoint_and_why_it_is_not_the_archive() -> None:
    """The reason travels with the artifact, not only with the commit message."""
    source = str(_artifact()["station_source"])
    assert "/v3/sensors/{id}/hours" in source
    assert "archive" in source and "computed mean" in source


# --- the request URL, which nothing tested until it failed live ---------------


def test_the_station_url_does_not_restate_the_version_segment() -> None:
    """The fault that voided capture attempt 1, now asserted offline.

    ``CII_OPENAQ_BASE_URL`` carries the version, and the endpoint constant used to
    carry it as well, so the first live call went to /v3/v3/sensors/80/hours and
    returned 404. Every other test in this module works from a response inwards;
    none of them built a URL, so the one thing deciding whether a response arrives
    had no coverage at all.
    """
    from capture_window import station_url

    url = station_url("https://api.openaq.org/v3", 80, START, END, 1)
    assert url.startswith("https://api.openaq.org/v3/sensors/80/hours?")
    assert "/v3/v3/" not in url


def test_the_station_url_matches_the_shipped_adapter() -> None:
    """The adapter has always built this correctly; the capture must agree with it.

    Asserted against the adapter's own construction rather than against a string
    written here, so the two cannot drift apart later in the direction that
    already cost one attempt.
    """
    from capture_window import station_url
    from climate_index.adapters.openaq.source import OpenAQStationSource

    base = "https://api.openaq.org/v3"
    source = OpenAQStationSource(base_url=base, api_key="x", sensors=(), lag_hours=48)
    adapter_path = f"{source._base_url}/sensors/80/hours"
    assert station_url(base, 80, START, END, 1).split("?")[0] == adapter_path


def test_the_station_url_carries_the_window_and_the_page() -> None:
    from capture_window import station_url

    url = station_url("https://api.openaq.org/v3/", 11, START, END, 3)
    assert f"datetime_from={_stamp(START).replace(':', '%3A')}" in url
    assert "page=3" in url
    assert "limit=1000" in url
    # A trailing slash on the base must not double the separator either.
    assert "//sensors" not in url.replace("https://", "")


# --- voided attempts, and why they are recorded rather than discarded ----------


def test_a_voided_attempt_is_recorded_and_its_data_removed(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """One clean run or void and start again. The attempt survives, the data does not.

    A capture assembled from two runs would carry a status distribution
    describing two runs and timestamp bounds that could straddle them. So the
    partial data is deleted, and the attempt is written down instead: a record
    showing two attempts and one capture is more honest than one showing a
    capture.
    """
    import capture_window

    monkeypatch.setattr(capture_window, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(capture_window, "CAPTURE_DIR", tmp_path / "capture")
    partial = tmp_path / "capture" / "control"
    partial.mkdir(parents=True)
    (partial / "station.jsonl").write_text('{"ts": "x"}\n')

    log = capture_window.CallLog()
    log.record(200)
    log.record(429)
    capture_window.record_void("control", "returned 429", log, capture_window.CallLog())

    assert not partial.exists(), "a voided attempt left its data on disk"
    history = capture_window.void_history("control")
    assert len(history) == 1
    assert history[0]["reason"] == "returned 429"
    assert history[0]["station"]["rate_limited"] is True
    assert history[0]["station"]["statuses"] == {"200": 1, "429": 1}


def test_a_second_void_appends_rather_than_replacing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Otherwise the history says one attempt however many there were."""
    import capture_window

    monkeypatch.setattr(capture_window, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(capture_window, "CAPTURE_DIR", tmp_path / "capture")
    log = capture_window.CallLog()
    capture_window.record_void("control", "first", log, log)
    capture_window.record_void("control", "second", log, log)
    assert [entry["reason"] for entry in capture_window.void_history("control")] == [
        "first",
        "second",
    ]


def test_no_void_history_reads_as_empty_rather_than_failing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import capture_window

    monkeypatch.setattr(capture_window, "EVIDENCE_DIR", tmp_path / "evidence")
    assert capture_window.void_history("control") == []


def test_the_artifact_carries_the_void_history_even_when_it_is_empty() -> None:
    """Absent and empty are different claims about how many runs were voided."""
    assert _artifact()["voided_attempts"] == []


# --- rate-limit headers, recorded from the run --------------------------------


def test_rate_limit_headers_are_kept_from_the_first_and_last_response() -> None:
    from capture_window import CallLog

    log = CallLog()
    log.record(200, {"x-ratelimit-remaining": "59"})
    log.record(200, {"x-ratelimit-remaining": "31"})
    log.record(200, {"x-ratelimit-remaining": "4"})
    record = log.as_dict()
    assert record["rate_limit_at_start"] == {"x-ratelimit-remaining": "59"}
    assert record["rate_limit_at_end"] == {"x-ratelimit-remaining": "4"}


def test_an_unsent_rate_limit_block_is_absent_rather_than_zeroed() -> None:
    """A field that cannot be filled from what happened is omitted, not assumed."""
    from capture_window import CallLog

    log = CallLog()
    log.record(200)
    record = log.as_dict()
    assert "rate_limit_at_start" not in record
    assert "rate_limit_at_end" not in record
    assert record["calls"] == 1


def test_only_the_documented_rate_limit_headers_are_recorded() -> None:
    """The artifact is committed, so it carries no header nobody asked for."""
    from capture_window import _rate_limit

    kept = _rate_limit({"x-ratelimit-remaining": "9", "set-cookie": "session=secret"})
    assert kept == {"x-ratelimit-remaining": "9"}
    assert _rate_limit(None) == {}


# --- the window is named, never dated -----------------------------------------


def test_the_capture_requires_an_explicit_window_and_offers_only_control() -> None:
    choices = tuple(sorted(Settings(_env_file=None).reconciliation_windows))
    assert choices == ("control",)
    parser = build_parser(choices)
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--window", "holdout"])
    assert parser.parse_args(["--window", "control"]).window == "control"


def test_the_capture_takes_no_date_arguments_at_all() -> None:
    """A date argument would be a route around the named-window restriction."""
    parser = build_parser(("control",))
    flags = {action.option_strings[0] for action in parser._actions if action.option_strings}
    assert flags == {"-h", "--window"}


# --- the validity gate must count what it removes ------------------------------


def test_the_gate_counts_every_reason_it_removed_an_hour() -> None:
    """A gate that filters without counting cannot report whether it ever fired.

    Section 5 pre-commits to reporting, during the measurement, how many hours
    carried hasFlags true, how many reported observedCount below one, and how
    many came back with a null value. The first control capture filtered on all
    three and counted none of them, so two of the three figures are unavailable
    for that window. This is the repair.
    """
    from collections import Counter

    from capture_window import station_rows

    payload = {
        "results": [
            _hour(_stamp(INSIDE), 12.5),
            _hour(_stamp(INSIDE), 12.5, flags=True),
            _hour(_stamp(INSIDE), 12.5, observed=0),
            _hour(_stamp(INSIDE), None),  # type: ignore[arg-type]
            "nonsense",
        ]
    }
    gate: Counter[str] = Counter()
    rows = station_rows(payload, SENSOR, gate)
    assert len(rows) == 1
    assert gate["returned"] == 5
    assert gate["retained"] == 1
    assert gate["has_flags_true"] == 1
    assert gate["observed_count_below_one"] == 1
    assert gate["null_value"] == 1
    assert gate["malformed"] == 1


def test_the_gate_tally_accounts_for_every_returned_row() -> None:
    """Returned must equal retained plus every removal reason, or one is unnamed."""
    from collections import Counter

    from capture_window import station_rows

    payload = {
        "results": [
            _hour(_stamp(INSIDE), 1.0),
            _hour(_stamp(INSIDE), 2.0, flags=True),
            _hour(_stamp(INSIDE), 3.0, observed=0),
        ]
    }
    gate: Counter[str] = Counter()
    station_rows(payload, SENSOR, gate)
    removed = sum(v for k, v in gate.items() if k not in ("returned", "retained"))
    assert gate["returned"] == gate["retained"] + removed


# --- hour alignment: applying the frozen rule, not extending it ----------------


def test_a_period_anchored_off_the_hour_is_rejected_and_counted() -> None:
    """Not a new validity gate. The frozen alignment quantifies over [H, H+1).

    hasFlags and observedCount filter admissible hours from among rows that are
    hours. A period anchored at :30 is not [H, H+1) for any integer H, so the
    rule defines no comparison for it and there is no H on the model side to pair
    it with. Rejecting applies the rule.
    """
    from collections import Counter

    from capture_window import station_rows

    off = INSIDE.replace(minute=30)
    payload = {"results": [_hour(_stamp(INSIDE), 12.5), _hour(_stamp(off), 9.9)]}
    gate: Counter[str] = Counter()
    misaligned: dict[str, int] = {}
    rows = station_rows(payload, SENSOR, gate, misaligned)
    assert len(rows) == 1
    assert rows[0]["ts"] == _stamp(INSIDE)
    assert gate["period_not_hour_aligned"] == 1
    assert misaligned == {"Amsterdam/s-11": 1}


def test_the_off_hour_rejection_keeps_the_seal_at_the_window_end() -> None:
    """The end boundary is the part that matters, and it is not tidiness.

    A period anchored at :30 straddling the control window's exclusive end
    contains thirty minutes of holdout time. Keeping such a row would import
    holdout minutes into a control capture through a rounding convention nobody
    wrote down.
    """
    from collections import Counter

    from capture_window import station_rows

    straddling = END.replace(minute=30) - timedelta(hours=1)
    assert straddling < END < straddling + timedelta(hours=1)
    gate: Counter[str] = Counter()
    rows = station_rows({"results": [_hour(_stamp(straddling), 11.0)]}, SENSOR, gate, {})
    assert rows == []
    assert gate["period_not_hour_aligned"] == 1


def test_off_hour_counts_fold_to_cities_so_a_concentration_is_visible() -> None:
    """If the exclusion sits mostly in one city it changes that city's coverage."""
    from capture_window import _by_city_counts

    assert _by_city_counts({"Madrid/a": 3, "Madrid/b": 2, "Delhi/c": 1}) == {
        "Delhi": 1,
        "Madrid": 5,
    }


def test_a_period_starting_on_the_hour_but_not_one_hour_long_is_rejected() -> None:
    """[23:00, 00:30) starts on the hour and is still not [H, H+1).

    Counted under its own reason, not folded into the anchor one, so the two
    failure shapes stay distinguishable in the report. An anchor-only check would
    pass this, and only three sensors of roughly two hundred had ever been looked
    at directly.
    """
    from collections import Counter

    from capture_window import station_rows

    entry = _hour(_stamp(INSIDE), 12.5)
    entry["period"]["datetimeTo"] = {"utc": _stamp(INSIDE + timedelta(minutes=90))}
    gate: Counter[str] = Counter()
    assert station_rows({"results": [entry]}, SENSOR, gate, {}) == []
    assert gate["period_not_one_hour_long"] == 1
    assert gate["period_not_hour_aligned"] == 0


def test_a_well_formed_hour_carries_its_end_and_is_kept() -> None:
    """The no-fault control: a check that rejects everything proves nothing."""
    from collections import Counter

    from capture_window import station_rows

    gate: Counter[str] = Counter()
    rows = station_rows({"results": [_hour(_stamp(INSIDE), 12.5)]}, SENSOR, gate, {})
    assert len(rows) == 1
    assert gate["period_not_one_hour_long"] == 0


def test_two_rows_for_one_station_hour_block_the_capture() -> None:
    """The join key for the whole measurement, never checked until now.

    A station returning two rows for one hour doubles its weight in a median over
    three stations, and the count would look like coverage.
    """
    from capture_window import assert_one_row_per_station_hour

    rows = [
        {"station_id": "s-11", "ts": _stamp(INSIDE)},
        {"station_id": "s-11", "ts": _stamp(INSIDE)},
        {"station_id": "s-12", "ts": _stamp(INSIDE)},
    ]
    with pytest.raises(CaptureFault, match="appear more than once"):
        assert_one_row_per_station_hour(rows)


def test_distinct_station_hours_pass_the_uniqueness_check() -> None:
    from capture_window import assert_one_row_per_station_hour

    assert_one_row_per_station_hour(
        [
            {"station_id": "s-11", "ts": _stamp(INSIDE)},
            {"station_id": "s-11", "ts": _stamp(LATER)},
            {"station_id": "s-12", "ts": _stamp(INSIDE)},
        ]
    )


# --- every breakdown must sum to its total ------------------------------------


def test_a_breakdown_that_does_not_sum_blocks_the_capture() -> None:
    """The defect that produced 0 beside a gate total of 3139, made a test.

    A breakdown reading zero with no total beside it is invisible. This is the
    check that makes it loud, and it exists because the invisible version already
    happened and was read as "no concentration" rather than "not recorded".
    """
    from capture_window import assert_breakdowns_sum

    record = {
        "validity_gate": {"returned": 100, "retained": 90, "period_not_hour_aligned": 10},
        "period_not_hour_aligned": {"rows": 0, "by_station": {}, "by_city": {}},
    }
    with pytest.raises(CaptureFault, match="off-hour breakdown does not sum|disagree"):
        assert_breakdowns_sum(record)


def test_a_consistent_record_passes_the_sum_check() -> None:
    """The no-fault control. A check that rejects everything proves nothing."""
    from capture_window import assert_breakdowns_sum

    assert_breakdowns_sum(
        {
            "validity_gate": {"returned": 100, "retained": 90, "period_not_hour_aligned": 10},
            "period_not_hour_aligned": {
                "rows": 10,
                "by_station": {"Delhi/a": 6, "Delhi/b": 4},
                "by_city": {"Delhi": 10},
            },
            "sensor_resolution": {
                "locations_admitted": 5,
                "resolved_to_pm25_sensor": 3,
                "refused": 2,
                "refusals_by_kind": {"no_pm25_sensor": 1, "none_covering_window": 1},
            },
            "observed_bounds": {"station": {"rows": 90}},
        }
    )


def test_the_gate_total_must_equal_retained_plus_every_reason() -> None:
    from capture_window import assert_breakdowns_sum

    with pytest.raises(CaptureFault, match="gate breakdown does not sum"):
        assert_breakdowns_sum({"validity_gate": {"returned": 100, "retained": 80, "flags": 10}})


def test_refusals_must_equal_their_by_kind_total() -> None:
    from capture_window import assert_breakdowns_sum

    with pytest.raises(CaptureFault, match="disagree with by-kind total"):
        assert_breakdowns_sum(
            {
                "sensor_resolution": {
                    "locations_admitted": 3,
                    "resolved_to_pm25_sensor": 1,
                    "refused": 2,
                    "refusals_by_kind": {"no_pm25_sensor": 1},
                }
            }
        )


# --- a city excluded by alignment is not a city that is absent -----------------


def test_alignment_exclusion_and_absence_are_recorded_as_different_facts() -> None:
    """Delhi and Lagos both end UNCHECKED and are not the same fact."""
    from dataclasses import dataclass

    from capture_window import city_exclusion_reasons

    @dataclass
    class Loc:
        city: str

    admitted = [Loc("Delhi"), Loc("Lagos"), Loc("Madrid")]
    retained = [{"city": "Madrid"}]
    reasons = city_exclusion_reasons(admitted, retained, {"Delhi/a": 2037})
    assert "Madrid" not in reasons
    assert "cannot express" in reasons["Delhi"]
    assert "no admitted location served" in reasons["Lagos"]
    assert reasons["Delhi"] != reasons["Lagos"]


# --- the resolver: exactly one covering candidate, or a named refusal ----------


def test_exactly_one_covering_candidate_is_taken() -> None:
    from climate_index.adapters.openaq.admission import choose_pm25_sensor

    assert choose_pm25_sensor([12234796], 50, [396, 12234796]) == 12234796


def test_no_covering_candidate_is_refused_not_guessed() -> None:
    from climate_index.adapters.openaq.admission import SensorIdentityError, choose_pm25_sensor

    with pytest.raises(SensorIdentityError, match="none covering the capture window"):
        choose_pm25_sensor([], 50, [396])


def test_two_covering_candidates_are_refused_as_ambiguous() -> None:
    """Not a tie to be broken by list order. A question the capture cannot answer."""
    from climate_index.adapters.openaq.admission import AmbiguousSensorError, choose_pm25_sensor

    with pytest.raises(AmbiguousSensorError, match="refusing to choose"):
        choose_pm25_sensor([1, 2], 50, [1, 2])


def test_the_bracket_rule_reads_the_sensors_own_dates() -> None:
    from climate_index.adapters.openaq.admission import brackets_window

    live = {"datetimeFirst": {"utc": "2025-01-01T00:00:00Z"}, "datetimeLast": {"utc": _stamp(END)}}
    dead = {
        "datetimeFirst": {"utc": "2016-02-05T14:55:00Z"},
        "datetimeLast": {"utc": "2018-02-21T21:15:00Z"},
    }
    assert brackets_window(live, START, END)
    assert not brackets_window(dead, START, END)
    assert not brackets_window({}, START, END)
