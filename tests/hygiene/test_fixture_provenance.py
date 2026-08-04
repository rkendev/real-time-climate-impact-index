"""Fixture files carry no key, and no measured value under an unusable licence.

Two controls, both attached to the artifact rather than to an activity.

The key control is obvious. The licence control exists because the frozen rule
("raw station values may be committed as fixtures only from providers whose
licence permits redistribution") was written as a rule about *the capture*, and
was then broken during a hand transcription, which is the same act under a
different name. A rule attached to an activity cannot catch that. A control
attached to the artifact can, and it fails on its own rather than depending on
anyone remembering.

Unstated terms are not permissive. A provider publishing ``licenses: null`` is a
provider whose terms are unknown, which is the case the rule exists for.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.unit import openaq_fixtures

_TESTS = Path(__file__).resolve().parents[1]
# A fixture module is any tests/**/*fixtures*.py. Derived by walking the tree
# rather than listed, because a list is a second place that has to be updated and
# the failure mode is not an empty scope but a populated and stale one: the scan
# reads real files, reports green, and is looking at the wrong set.
#
# This repository has now produced that failure three times. The pre-commit gate
# read tracked files only; the holdout scan used `git ls-files` and so could not
# see a brand-new entry point; and this very tuple was hardcoded one commit ago,
# which would have left the next fixture module outside the licence control
# entirely. Every one of them was green while looking at the wrong set.
#
# `test_the_scan_covers_a_fixture_file_it_has_never_seen` proves the derivation by
# creating a file and watching the scope grow, which is the only check that
# distinguishes a live scope from a stale one.
FIXTURE_GLOB = "*fixtures*.py"


def fixture_files() -> tuple[Path, ...]:
    """Every committed fixture module, derived from the tree at call time."""
    return tuple(sorted(_TESTS.rglob(FIXTURE_GLOB)))


# Licences whose redistributionAllowed flag has been checked on /v3/licenses.
# Adding one means checking that flag first, not assuming it.
# SYNTHETIC means the fixture carries invented numbers and no licensed
# measurement, so no provider's terms apply to it.
PERMITTED_LICENCES = frozenset({"ODC-BY", "SYNTHETIC"})

HEADER_NAME = "X-" + "API-Key"
# The header name *carrying a value*, which is what a recorded request looks
# like: the name, an optional closing quote, a colon, then something. A bare
# mention is allowed and there is one legitimate instance, the observed 401 body
# whose message names the header in prose. Banning the bare name outright would
# force that transcription to be altered, and a fixture edited to satisfy a
# scanner is no longer a transcription.
HEADER_WITH_VALUE = re.compile(re.escape(HEADER_NAME) + r'"?\s*:\s*\S')
# A long unbroken alphanumeric run, which is what an OpenAQ key looks like and
# what no legitimate fixture literal in this repository contains.
KEY_SHAPED = re.compile(r"[A-Za-z0-9]{32,}")


def _measured_value_fixtures() -> dict[str, dict[str, object]]:
    """Module-level fixture dicts that carry a measured value."""
    found: dict[str, dict[str, object]] = {}
    for name in dir(openaq_fixtures):
        if name.startswith("_") or name.isupper() is False:
            continue
        value = getattr(openaq_fixtures, name)
        if isinstance(value, dict) and "value" in value:
            found[name] = value
    return found


def test_no_fixture_file_carries_a_key_or_the_header_name() -> None:
    for path in fixture_files():
        text = path.read_text()
        carried = HEADER_WITH_VALUE.search(text)
        assert carried is None, f"{path.name} carries the key header with a value"
        hits = [m.group(0) for m in KEY_SHAPED.finditer(text)]
        assert not hits, f"{path.name} carries a key-shaped token: {hits[:2]}"


def test_every_measured_value_declares_its_source() -> None:
    """A fixture carrying a value with no declaration is the uncaught case."""
    declared = set(openaq_fixtures.MEASURED_VALUE_SOURCES)
    carrying = set(_measured_value_fixtures())
    undeclared = sorted(carrying - declared)
    assert not undeclared, f"fixtures carry measured values but declare no source: {undeclared}"


def test_every_declared_source_is_on_the_permitted_licence_list() -> None:
    for name, source in openaq_fixtures.MEASURED_VALUE_SOURCES.items():
        licence = source.get("licence")
        assert licence in PERMITTED_LICENCES, (
            f"{name} carries values from station {source.get('location_id')} "
            f"under licence {licence!r}, which is not on the permitted list "
            f"{sorted(PERMITTED_LICENCES)}. Unstated terms are not permissive."
        )
        if licence != "SYNTHETIC":
            assert source.get("location_id"), f"{name} declares no station id"
        else:
            assert source.get("synthetic") is True, f"{name} claims SYNTHETIC without saying so"


def test_the_at13_fixture_declares_itself_synthetic() -> None:
    """It commits no licensed measurement, and it has to say so where it lives.

    The licence rule bites on committed raw values, not on use, so a fixture of
    invented numbers is outside it. That is only true while the numbers really
    are invented, which is a claim the module makes in writing rather than one a
    reader has to infer from the values looking round.
    """
    from tests.integration import at13_fixtures

    assert "SYNTHETIC" in at13_fixtures.VALUE_PROVENANCE
    assert "Every value here is synthetic" in (at13_fixtures.__doc__ or "")


def test_the_scan_reaches_the_fixtures_it_claims_to() -> None:
    """Neither absence test may pass vacuously."""
    found = fixture_files()
    assert found, "the fixture scan found no files at all"
    for path in found:
        assert path.is_file(), path
    assert _measured_value_fixtures(), "no fixture carrying a measured value was found"
    # The key-shaped scan must be able to fire, or a clean tree and a broken
    # regex look the same.
    assert KEY_SHAPED.search("k" * 32)
    assert HEADER_WITH_VALUE.search(f'"{HEADER_NAME}": "x"')
    assert ast.parse(found[0].read_text()).body


def test_the_scan_covers_a_fixture_file_it_has_never_seen(tmp_path: Path) -> None:
    """The scope is live, not stale, proven by adding a member and watching it grow.

    Non-emptiness would not have caught any of the three scope failures this
    repository has had: in every one the scan read real files and reported green
    while looking at the wrong set. The only check that separates a live scope
    from a populated stale one is to add something and see whether it is noticed.

    A file is created inside the scanned tree, its own directory is removed
    afterwards, and the assertion is that the derivation picked it up and that
    the key control then fired on its contents.
    """
    new_dir = _TESTS / "_scope_probe"
    new_dir.mkdir(exist_ok=True)
    probe = new_dir / "probe_fixtures.py"
    try:
        probe.write_text('SECRET = "' + "k" * 40 + '"\n')
        assert probe in fixture_files(), "a new fixture module was not picked up by the scan"
        # And the control really reads it rather than merely listing it.
        hits = [m.group(0) for m in KEY_SHAPED.finditer(probe.read_text())]
        assert hits, "the key control did not fire on the probe's contents"
    finally:
        probe.unlink(missing_ok=True)
        new_dir.rmdir()
    assert probe not in fixture_files()
