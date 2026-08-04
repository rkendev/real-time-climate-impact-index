"""The holdout is not opened. Successor to the negative-space exclusion control.

``test_no_reconciliation_yet.py`` forbade comparison outright and was deleted in
the commit that introduced the tolerance, which is what dates the end of the
exclusion period. That commit is also the moment the risk peaks: comparison
becomes possible for the first time, and the only automated guard against it goes
away in the same breath. So this file lands in that same commit. A retirement
that leaves a gap is worse than no retirement.

It no longer forbids comparison. It forbids comparison *over the holdout*, in
four independent ways, so that no single mistake opens the seal:

1. the entry point requires an explicit window and offers no default;
2. the holdout is not nameable, because the settings object holds only the
   control window and the entry point accepts only what it holds;
3. no holdout data exists on disk, and the capture artifacts say so both in what
   they declare and in the timestamps they actually wrote;
4. no holdout date appears anywhere on the run surface.

The forbidden range is parsed out of the contract rather than written here, so
this file states the rule in one place only and cannot drift from it.

Layer 3 is two assertions rather than one on purpose. Checking only what an
artifact declares would catch a mislabelled pull and not a mis-executed one, so
the realized minimum and maximum observation timestamps are checked as well:
"we asked for the control window" and "what landed is the control window" are
separately established. ``reconcile``'s own window assertion is the third layer
and is left as defence in depth rather than as the only check.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.hygiene.test_settings_match_contract import contract_text, parse_split

from climate_index.config import Settings
from climate_index.core.reconciliation import WindowViolationError, reconcile

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = REPO_ROOT / "data" / "capture"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "capture"

# What a reconciliation run can be pointed at: source, operator tooling, tests,
# the command surface and the environment example. Deliberately not the whole
# tree.
#
# docs/ is excluded, and the exclusion is named rather than assumed, because two
# tracked files carry dates inside the holdout range for reasons that are not
# comparisons and that predate this work:
#
#   * the Phase 2 teardown evidence under docs/evidence/teardown-2026-07 carries
#     three consecutive daily cloud cost lines that fall inside the range. They
#     are billing figures from an AWS run, and no station or model value was
#     within a month of existing when they were written;
#   * the pinned station-admission artifact carries the capture window's end as
#     capture_window_end. That instant is the exclusive end of the holdout and so
#     falls outside it by construction, but a naive scan would still see the
#     month and day.
#
# The contract, ADR-0009 and the runbook all state the split in prose, which is
# where the rule is supposed to live. A scan whose exclusions are undocumented is
# a scan nobody can audit, so they are documented here. The dates themselves are
# deliberately not spelled out above: this file names the holdout only through
# the contract, which the test at the end of the file enforces against this
# comment too.
RUN_SURFACE = (
    "src",
    "scripts",
    "tests",
    "Makefile",
    ".env.example",
)


def holdout_span() -> tuple[datetime, datetime]:
    """The forbidden range, read out of the contract and not restated here."""
    return parse_split(contract_text())["holdout"]


def holdout_dates() -> tuple[str, ...]:
    """Every calendar date inside the half-open holdout, as ``YYYY-MM-DD``."""
    start, end = holdout_span()
    days = (end - start).days
    return tuple(
        (start.replace(hour=0) + (end - start) / days * index).strftime("%Y-%m-%d")
        for index in range(days)
    )


def _tracked_files() -> list[Path]:
    """Every file on the run surface, including ones not yet committed.

    ``--others --exclude-standard`` is load-bearing rather than tidy. Without it
    the scan sees tracked files only, so a new and uncommitted file is invisible
    to it, and a new file is exactly what a reconciliation entry point is when it
    first appears. This was not a hypothetical: the first version of this control
    scanned tracked files alone and passed over a holdout date appended to the
    then-untracked entry point. The red proof caught it, a green would not have.

    ``--exclude-standard`` keeps .gitignore honoured, so the virtual environment
    and the capture directory stay out of the scan.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", *RUN_SURFACE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout; the run surface cannot be enumerated")
    return [REPO_ROOT / name for name in result.stdout.split("\0") if name]


def scan_for_holdout_dates(text: str) -> list[str]:
    """Which holdout dates appear in ``text``. The detector, shared with its proof."""
    return [date for date in holdout_dates() if date in text]


def test_the_entry_point_requires_an_explicit_window() -> None:
    """No default. A run always records which window it was pointed at."""
    import reconcile as entry_point

    parser = entry_point.build_parser(Settings(_env_file=None))
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_the_holdout_is_not_nameable() -> None:
    """The settings object holds the control window and nothing else."""
    import reconcile as entry_point

    settings = Settings(_env_file=None)
    assert set(settings.reconciliation_windows) == {"control"}
    assert entry_point.window_choices(settings) == ("control",)

    parser = entry_point.build_parser(settings)
    with pytest.raises(SystemExit):
        parser.parse_args(["--window", "holdout"])

    with pytest.raises(entry_point.ApparatusFault, match="no window named"):
        entry_point.resolve_window("holdout", settings)


def test_pointing_the_rule_at_a_holdout_hour_is_refused() -> None:
    """The third layer: even called directly, a stray holdout hour stops the run.

    Refused rather than filtered out. Dropping the stray hour silently would let
    a run labelled with the control window quietly measure part of the holdout,
    which is the failure the window argument exists to prevent.
    """
    from climate_index.core.models import Construction, StationObservation

    settings = Settings(_env_file=None)
    control = settings.reconciliation_windows["control"]
    start, _ = holdout_span()
    stray = StationObservation(
        ts=start,
        region="EUR",
        city="Amsterdam",
        station_id="probe",
        pm25_ugm3=10.0,
        sample_count=1,
        construction=Construction.PROVIDER_HOURLY,
    )
    with pytest.raises(WindowViolationError):
        reconcile([], [stray], [], settings, window=control)


def test_no_holdout_capture_exists_on_disk() -> None:
    """Absence is checkable. Restraint is not."""
    for name in ("holdout", *holdout_dates()):
        assert not (CAPTURE_DIR / name).exists(), f"a holdout capture exists at {name}"
    if CAPTURE_DIR.is_dir():
        assert {path.name for path in CAPTURE_DIR.iterdir()} <= {"control"}


def check_capture_artifact(record: dict[str, object], name: str) -> None:
    """The detector, shared by the real artifacts and by its own red proof.

    Two assertions, not one. The declared window catches a mislabelled pull. The
    realized maximum catches a mis-executed one, which the declaration alone
    would not: metadata saying "control window" is not the same as data that is
    one.
    """
    start, _ = holdout_span()
    requested = record.get("window_requested") or {}
    assert isinstance(requested, dict)
    assert requested.get("name") == "control", f"{name} declares a non-control window"
    observed = record.get("observed_bounds") or {}
    assert isinstance(observed, dict)
    assert observed, f"{name} records no realized bounds, so only its label was checked"
    for source, bounds in observed.items():
        assert isinstance(bounds, dict)
        if bounds.get("max") is None:
            continue
        realized = datetime.fromisoformat(str(bounds["max"]).replace("Z", "+00:00"))
        assert realized.astimezone(UTC) < start, (
            f"{name} wrote a {source} observation at {realized.isoformat()}, "
            f"which is inside the holdout"
        )


def check_void_history(entries: list[dict[str, object]], name: str) -> None:
    """A voided attempt must not have been aimed at the holdout either.

    Voided attempts are a different shape from capture artifacts: a list of
    attempts, each with a reason and its call logs, and no window declaration of
    its own. The window it was aimed at is in the filename. Both shapes live in
    the same directory and both are checked, because an attempt that reached for
    the holdout and failed is still an attempt that reached for the holdout.
    """
    assert name.startswith("voided-"), name
    aimed_at = name.removeprefix("voided-").removesuffix(".json")
    assert aimed_at == "control", f"{name} records attempts on a non-control window"
    # The one documented exception, and it is narrow: the *full* instant at which
    # the control window ends. That instant is the control window's exclusive end
    # and the holdout's inclusive start, so as a boundary it denotes where the
    # control window stops rather than any holdout content. Only the complete
    # timestamp is excused; the bare date is not. One committed void record cites
    # it, from a fault message that no longer interpolates window bounds.
    boundary = holdout_span()[0].strftime("%Y-%m-%dT%H:%M:%SZ")
    for index, entry in enumerate(entries):
        assert isinstance(entry, dict), f"{name} entry {index} is not an attempt record"
        found = scan_for_holdout_dates(json.dumps(entry).replace(boundary, "<window-end>"))
        assert not found, f"{name} entry {index} references holdout dates {found}"


def _evidence_files() -> list[Path]:
    """Derived by walking, so a new artifact is covered without an edit here.

    Split by shape rather than assumed to be uniform. The first real run of this
    control crashed with an AttributeError because the void history had been added
    to this directory in a later commit than the glob, and a list arrived where a
    dict was expected. A control that raises on an unfamiliar shape has not
    checked it, and the difference between "checked and clean" and "crashed before
    checking" is the whole point of having the control.
    """
    if not EVIDENCE_DIR.is_dir():
        return []
    return sorted(EVIDENCE_DIR.glob("*.json"))


def _capture_artifacts() -> list[Path]:
    return [path for path in _evidence_files() if not path.name.startswith("voided-")]


def _void_histories() -> list[Path]:
    return [path for path in _evidence_files() if path.name.startswith("voided-")]


def test_no_capture_artifact_declares_or_contains_a_holdout_hour() -> None:
    for artifact in _capture_artifacts():
        check_capture_artifact(json.loads(artifact.read_text()), artifact.name)


def test_no_voided_attempt_was_aimed_at_the_holdout() -> None:
    for history in _void_histories():
        check_void_history(json.loads(history.read_text()), history.name)


def test_every_evidence_file_is_covered_by_one_of_the_two_checks() -> None:
    """No file in the directory may be checked by neither, which is how one was.

    The two checks above each walk their own subset. Without this, a third shape
    arriving later would be scanned by neither and nothing would say so: the
    directory would keep reporting green over a file nobody looked at. That is the
    stale-scope failure again, in a directory rather than a file list.
    """
    every = set(_evidence_files())
    covered = set(_capture_artifacts()) | set(_void_histories())
    assert every == covered, f"evidence files checked by neither: {sorted(every - covered)}"


def test_the_artifact_check_would_notice_both_ways_of_reaching_the_holdout() -> None:
    """This absence test passes over zero artifacts today, so it is proven here.

    Before the capture has run there is nothing on disk for the check above to
    read, which is precisely when an unproven detector is indistinguishable from
    a working one. Both failure routes are exercised against synthetic records.
    """
    start, _ = holdout_span()
    inside = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    before = (start.replace(hour=0) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    good = {
        "window_requested": {"name": "control"},
        "observed_bounds": {"station": {"max": before}, "model": {"max": before}},
    }
    check_capture_artifact(good, "synthetic-good")

    mislabelled = {**good, "window_requested": {"name": "holdout"}}
    with pytest.raises(AssertionError, match="declares a non-control window"):
        check_capture_artifact(mislabelled, "synthetic-mislabelled")

    misexecuted = {
        "window_requested": {"name": "control"},
        "observed_bounds": {"station": {"max": inside}, "model": {"max": before}},
    }
    with pytest.raises(AssertionError, match="inside the holdout"):
        check_capture_artifact(misexecuted, "synthetic-misexecuted")

    # An artifact that records no realized bounds at all would otherwise satisfy
    # the label check and be waved through on its declaration alone.
    with pytest.raises(AssertionError, match="records no realized bounds"):
        check_capture_artifact({"window_requested": {"name": "control"}}, "synthetic-bare")


def test_the_void_history_check_would_notice_an_attempt_at_the_holdout() -> None:
    """Proven the same way, because a voided attempt is still an attempt."""
    start, _ = holdout_span()
    clean = [{"reason": "returned 404", "voided_at": "2026-08-04T14:13:59Z"}]
    check_void_history(clean, "voided-control.json")

    with pytest.raises(AssertionError, match="non-control window"):
        check_void_history(clean, "voided-holdout.json")

    reaching = [{"reason": f"datetime_from={start.strftime('%Y-%m-%d')} returned 500"}]
    with pytest.raises(AssertionError, match="references holdout dates"):
        check_void_history(reaching, "voided-control.json")


def test_no_holdout_date_appears_on_the_run_surface() -> None:
    found: list[str] = []
    for path in _tracked_files():
        if path == Path(__file__):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        found += [f"{path.relative_to(REPO_ROOT)}: {date}" for date in scan_for_holdout_dates(text)]
    assert not found, f"holdout dates on the run surface: {found}"


def test_this_file_names_the_holdout_only_through_the_contract() -> None:
    """No date literal here either, or the scan above would be excusing itself."""
    literals = re.findall(r"\d{4}-\d{2}-\d{2}", Path(__file__).read_text())
    assert not [date for date in literals if date in holdout_dates()]


def test_the_scan_covers_a_file_that_did_not_exist_when_it_was_written() -> None:
    """The scope is live, not stale, proven by adding a member and watching it grow.

    Non-emptiness is not the check. The failure this control already had was a
    populated but stale scope: it read 0 files of the entry point while reporting
    green, because `git ls-files` lists tracked files and a new entry point is
    untracked. A scan can be looking at a hundred real files and still be looking
    at the wrong set.

    So a file is created on the run surface and the scope is required to grow by
    it, and the detector is required to fire on its contents.
    """
    start, _ = holdout_span()
    probe = REPO_ROOT / "scripts" / "_scope_probe.py"
    try:
        probe.write_text(f"# {start.strftime('%Y-%m-%d')}\n")
        assert probe in _tracked_files(), "a new file on the run surface was not scanned"
        assert scan_for_holdout_dates(probe.read_text()), "the detector did not fire on it"
    finally:
        probe.unlink(missing_ok=True)
    assert probe not in _tracked_files()


def test_the_scan_would_notice_a_holdout_date() -> None:
    """The absence checks above must be able to fail, not pass vacuously."""
    start, _ = holdout_span()
    inside = start.strftime("%Y-%m-%d")
    assert scan_for_holdout_dates(f"window_start = '{inside}T04:00Z'") == [inside]
    assert scan_for_holdout_dates("nothing to see here") == []
    # The range itself must be non-empty and must have come from the contract.
    assert len(holdout_dates()) == 7
    assert _tracked_files(), "the scan reached no files"
    # And the parse the whole file rests on must really read the document.
    assert ast.parse(Path(__file__).read_text()) is not None
