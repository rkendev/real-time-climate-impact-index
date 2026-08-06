"""The holdout opened once, and nothing from before the opening has moved.

Successor to ``test_holdout_not_opened.py``, which asserted the holdout was not
nameable and no holdout capture existed. Adding the holdout entry to the settings
object makes both of those false, so that file is deleted in the same commit that
adds it and this one ships alongside. Deleting it without a replacement would
leave the project unguarded at the moment of the last irreversible act, which is
the trap the reconciliation control's retirement already had to avoid once.

The guard changes shape because the risk does. Before the opening the risk was
touching the holdout early. After it, the holdout number exists and cannot be
un-seen, and the two remaining risks are opening it *again* and quietly revising
what was written before it.

The second is the one that matters. Once a holdout rate exists there is pressure
to revisit the control-window write-up, the capture it rests on, or the contract
itself, and nothing else in this repository would detect a single character
changing in any of them.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "capture"
RUN_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "control-window"
HOLDOUT_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "holdout"
HASHES = REPO_ROOT / "docs" / "evidence" / "pre-opening-hashes.json"
ADR = REPO_ROOT / "adr" / "0009-openaq-disagreement-grading.md"

CONTROL_SECTION = "## The control-window run: the rate, and the freeze proved after it"
ADR_KEY = "adr/0009 :: control-window run disclosure"


def _hashes() -> dict[str, str]:
    if not HASHES.is_file():
        pytest.skip("no pre-opening hash record; the holdout has not been opened")
    loaded: dict[str, str] = json.loads(HASHES.read_text())["hashes"]
    return loaded


def control_disclosure_text() -> str:
    """The control-run disclosure section, isolated from the rest of the record.

    Hashing the whole ADR would forbid the record from growing, which is the
    opposite of what is wanted: the project must keep writing, and this one
    section must stop changing. So the section is extracted by its heading and
    hashed alone.
    """
    text = ADR.read_text()
    assert text.count(CONTROL_SECTION) == 1, "the control disclosure heading is not unique"
    start = text.index(CONTROL_SECTION)
    # The next top-level heading, not a named one. The first version of this ran
    # to "## Post-project findings", which is not a fixed boundary: every section
    # appended before it enlarged the extracted region, so the hash changed
    # whenever the record grew. The control fired on its own detector rather than
    # on a real edit, which is the failure mode a boundary must not have.
    following = re.search(r"\n## ", text[start + len(CONTROL_SECTION) :])
    assert following is not None, "no heading follows the control disclosure"
    return text[start : start + len(CONTROL_SECTION) + following.start() + 1]


# --- opened exactly once ------------------------------------------------------


def test_at_most_one_holdout_capture_artifact_exists() -> None:
    """One capture of the holdout, or none. Never two."""
    artifacts = [
        p for p in CAPTURE_EVIDENCE.glob("*holdout*.json") if not p.name.startswith("voided-")
    ]
    assert len(artifacts) <= 1, f"the holdout was captured more than once: {artifacts}"


def test_at_most_one_holdout_run_record_exists() -> None:
    """One reconciliation over the holdout, or none. Never two.

    The contract caps re-runs of the *control* window. The holdout is governed by
    a different clause and opens exactly once, so it carries no re-run allowance
    at all: not two, not one, zero.
    """
    runs = list(RUN_EVIDENCE.glob("*holdout*.json")) + (
        list(HOLDOUT_EVIDENCE.glob("*.json")) if HOLDOUT_EVIDENCE.is_dir() else []
    )
    named = [p for p in runs if "run" in p.name or "reconcil" in p.name]
    assert len(named) <= 1, f"the holdout was reconciled more than once: {named}"


def test_the_holdout_window_is_configured_exactly_once() -> None:
    from climate_index.config import Settings

    windows = Settings(_env_file=None).reconciliation_windows
    assert sorted(windows) == ["control", "holdout"], sorted(windows)


# --- nothing from before the opening has been altered since --------------------


@pytest.mark.parametrize(
    "relative",
    [
        "PREREGISTRATION.md",
        "docs/evidence/capture/2026-08-06-control.json",
        "docs/evidence/control-window/2026-08-06-control-run.json",
        "docs/evidence/control-window/rerun-counter.json",
        "docs/evidence/station-admission/2026-08-03.json",
    ],
)
def test_a_pre_opening_file_is_byte_identical(relative: str) -> None:
    """Checked by hash, so a one-character edit fails."""
    expected = _hashes()[relative]
    actual = hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
    assert actual == expected, f"{relative} changed after the holdout was opened"


def test_the_control_disclosure_is_unchanged_since_the_opening() -> None:
    """The section most under pressure once a holdout number exists."""
    expected = _hashes()[ADR_KEY]
    actual = hashlib.sha256(control_disclosure_text().encode()).hexdigest()
    assert actual == expected, "the control-window disclosure changed after the opening"


# --- both detectors proven red -------------------------------------------------


def test_the_duplicate_detectors_would_notice_a_second_opening(tmp_path: Path) -> None:
    """A second holdout artifact must fail, not be tolerated as an overwrite."""
    probe_a, probe_b = tmp_path / "a-holdout.json", tmp_path / "b-holdout.json"
    probe_a.write_text("{}")
    probe_b.write_text("{}")
    found = [p for p in tmp_path.glob("*holdout*.json") if not p.name.startswith("voided-")]
    assert len(found) == 2
    with pytest.raises(AssertionError):
        assert len(found) <= 1, "seeded: two holdout artifacts"


def test_the_hash_check_would_notice_a_one_character_edit() -> None:
    """The assertion that matters, seeded against the real disclosure text.

    One character is added to the control-window disclosure and the hash is
    required to change. This is what stands between a spent, disclosed result and
    a quietly improved one.
    """
    real = control_disclosure_text()
    tampered = real.replace(
        "An apparatus check and not a result.", "An apparatus check and not a result..", 1
    )
    assert tampered != real, "the seed changed nothing"
    assert hashlib.sha256(tampered.encode()).hexdigest() != _hashes()[ADR_KEY]


def test_the_hash_record_covers_every_file_it_should() -> None:
    """A hash record missing an entry is a hash record that guards less than it says."""
    recorded = set(_hashes())
    required = {
        "PREREGISTRATION.md",
        "docs/evidence/capture/2026-08-06-control.json",
        "docs/evidence/control-window/2026-08-06-control-run.json",
        "docs/evidence/control-window/rerun-counter.json",
        "docs/evidence/station-admission/2026-08-03.json",
        ADR_KEY,
    }
    assert required <= recorded, f"unguarded: {sorted(required - recorded)}"


# --- the drift check is complete, by argument plus a checked fact --------------


def test_no_sensor_is_shared_between_two_locations() -> None:
    """The fact that closes the multiset-comparison gap.

    Sensors are location-owned: the resolver picks only from a location's own
    sensor list, so a location cannot resolve to another location's sensor and a
    pairwise swap is impossible. Given that, comparing the multiset of resolved
    sensor ids is equivalent to comparing the mapping pair by pair, and the drift
    check between the control and holdout captures is complete rather than
    partial.

    This asserts the supporting fact rather than assuming it: every resolved
    sensor id appears against exactly one location.
    """
    artifacts = [
        p for p in CAPTURE_EVIDENCE.glob("*holdout*.json") if not p.name.startswith("voided-")
    ]
    if not artifacts:
        pytest.skip("no holdout capture yet")
    mapping = json.loads(artifacts[0].read_text())["admission"]["location_to_sensor"]
    assert len(set(mapping.values())) == len(mapping), "a sensor id is shared between locations"
    # And no sensor id equals its location id, which is the original fault's
    # signature and would mean the resolution step had been bypassed.
    assert not [loc for loc, sensor in mapping.items() if int(loc) == sensor]
