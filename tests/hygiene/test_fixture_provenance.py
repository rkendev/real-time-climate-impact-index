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
# Every committed fixture module carrying station-shaped or model-shaped numbers.
# A new fixture file is a new place a licensed measurement could be committed, so
# it is added here when it is written rather than left outside the scan. The
# AT-13 fixture is entirely synthetic and says so in its own docstring; it is
# listed anyway, because "we know it is clean" is the claim this control exists
# to replace.
FIXTURE_FILES = (
    _TESTS / "unit" / "openaq_fixtures.py",
    _TESTS / "integration" / "at13_fixtures.py",
)

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
    for path in FIXTURE_FILES:
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
    for path in FIXTURE_FILES:
        assert path.is_file(), path
    assert _measured_value_fixtures(), "no fixture carrying a measured value was found"
    # The key-shaped scan must be able to fire, or a clean tree and a broken
    # regex look the same.
    assert KEY_SHAPED.search("k" * 32)
    assert HEADER_WITH_VALUE.search(f'"{HEADER_NAME}": "x"')
    assert ast.parse(FIXTURE_FILES[0].read_text()).body
