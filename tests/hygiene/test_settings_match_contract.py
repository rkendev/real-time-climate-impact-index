"""The settings object must match the frozen contract, mechanically (section 9).

Section 9 makes the settings object the single authority for thresholds and
tunables and forbids a constant appearing in adapter code. The code has to hold
the numbers, so they now live in two places, and two places can disagree. This
test closes that by reading ``PREREGISTRATION.md`` out of the repository and
asserting the settings carry what it says.

Parsing the document rather than restating its values inline is the choice made
here, and it is safe for reasons specific to this document rather than in
general. The file is frozen at one commit, its section 10 permits only a proof to
move a predicate, and the values sit on rigid lines under headings that occur
once. Three things keep the parse honest rather than hopeful:

* the structural assertions below run before any value is read, so a layout
  change fails loudly instead of silently matching something else;
* the freeze assertion checks that the document really has not moved, which turns
  the ADR's prose claim into a mechanical one;
* the anti-vacuity test at the end runs the same parser over a document with
  different values and requires the comparison to fail.

The alternative, inline values with the commit cited in a comment, was declined.
It copies the numbers into a third place, which is the problem this test exists
to solve.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_index.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "PREREGISTRATION.md"

# The commit the contract was frozen at. Cited in ADR-0009 and in the
# specification; asserted here so the citation cannot rot.
FROZEN_AT = "b81f1c9"

THRESHOLD_HEADING = "### 4.1 The threshold"

# The PM2.5 row of the frozen threshold block. Anchored on the label so it cannot
# match a discussion of the constants elsewhere in the document.
_THRESHOLD = re.compile(
    r"PM2\.5:\s+Ur\(RV\)\s*=\s*([\d.]+)\s+RV\s*=\s*([\d.]+)\s*ug/m3"
    r"\s+a\s*=\s*([\d.]+)\s+beta\s*=\s*([\d.]+)"
)

_MIN_COVERAGE = re.compile(
    r"\*\*Minimum coverage.*?covered when at least (\d+) stations", re.DOTALL
)

_SPLIT = re.compile(
    r"the control window is `\[([0-9T:Z-]+),\s*([0-9T:Z-]+)\)`"
    r"\s*and the holdout is\s*`\[([0-9T:Z-]+),\s*([0-9T:Z-]+)\)`",
)


def contract_text() -> str:
    return CONTRACT.read_text()


def parse_threshold(text: str) -> dict[str, float]:
    """The four MQO constants, from section 4.1 and from nowhere else."""
    assert text.count(THRESHOLD_HEADING) == 1, "section 4.1's heading is not unique"
    section = text.split(THRESHOLD_HEADING, 1)[1].split("\n### ", 1)[0]
    matches = _THRESHOLD.findall(section)
    assert len(matches) == 1, f"expected one PM2.5 constants line in 4.1, found {len(matches)}"
    relative, reference, alpha, beta = matches[0]
    return {
        "relative": float(relative),
        "reference": float(reference),
        "alpha": float(alpha),
        "beta": float(beta),
    }


def parse_min_coverage(text: str) -> int:
    matches = _MIN_COVERAGE.findall(text)
    assert len(matches) == 1, f"expected one minimum-coverage rule, found {len(matches)}"
    return int(matches[0])


def parse_split(text: str) -> dict[str, tuple[datetime, datetime]]:
    matches = _SPLIT.findall(text)
    assert len(matches) == 1, f"expected one split rule, found {len(matches)}"
    control_start, control_end, holdout_start, holdout_end = matches[0]
    return {
        "control": (_moment(control_start), _moment(control_end)),
        "holdout": (_moment(holdout_start), _moment(holdout_end)),
    }


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_the_contract_is_still_frozen() -> None:
    """One commit, and the one the citations name.

    ADR-0009 and the specification both assert this in prose. Asserting it here
    means the assertion survives a later edit rather than describing one.
    """
    result = subprocess.run(
        ["git", "log", "--format=%H", "--", "PREREGISTRATION.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout; the freeze cannot be verified here")
    commits = result.stdout.split()
    assert len(commits) == 1, f"the contract has been edited: {len(commits)} commits"
    assert commits[0].startswith(FROZEN_AT), f"frozen at {commits[0]}, not {FROZEN_AT}"


def test_the_mqo_constants_match_section_4_1() -> None:
    frozen = parse_threshold(contract_text())
    settings = Settings(_env_file=None)
    assert settings.mqo_relative_uncertainty_at_reference == frozen["relative"]
    assert settings.mqo_reference_value_ugm3 == frozen["reference"]
    assert settings.mqo_alpha == frozen["alpha"]
    assert settings.mqo_beta == frozen["beta"]


def test_the_prose_contradiction_resolves_to_the_table() -> None:
    """Section 4.4 records that the prose says 0.30 and Table 7 says 0.50.

    The table binds. Pinned separately because the parse above would be equally
    happy with either number, and the whole point of section 4.4 is that a reader
    could take the wrong one.
    """
    assert Settings(_env_file=None).mqo_alpha == 0.50


def test_the_minimum_coverage_matches_section_5() -> None:
    assert Settings(_env_file=None).station_min_per_city_window == parse_min_coverage(
        contract_text()
    )


def test_the_control_window_matches_section_5() -> None:
    frozen = parse_split(contract_text())
    windows = Settings(_env_file=None).reconciliation_windows
    assert "control" in windows, "the control window is not configured"
    assert (windows["control"].start, windows["control"].end) == frozen["control"]


def test_the_annual_average_constants_are_absent() -> None:
    """Np and Nnp enter only the annual-average expression, which this does not use.

    Section 4.2 says so and says it is stated there so neither is carried into
    the implementation by mistake. This is that statement, enforced.
    """
    fields = set(Settings.model_fields)
    assert not [name for name in fields if "_np" in name or name.endswith("_nnp")]


def test_the_parser_would_notice_a_different_contract() -> None:
    """The parse must be able to fail, not pass vacuously.

    A regex that silently matched nothing, or a section split that returned the
    whole document, would look identical to a contract the settings satisfy. Each
    parser is run over a document carrying different values and must return them,
    which is what proves the comparisons above are load-bearing.
    """
    altered = (
        f"{THRESHOLD_HEADING}\n\n```\n"
        "  PM2.5:   Ur(RV) = 0.99     RV = 11 ug/m3     a = 0.30     beta = 7\n"
        "```\n\n"
        "**Minimum coverage, decided per window and not per city.** A city-window "
        "is covered when at least 9 stations report that hour.\n\n"
        "the control window is `[2020-01-01T00:00Z, 2020-01-08T00:00Z)` and the "
        "holdout is `[2020-01-08T00:00Z, 2020-01-15T00:00Z)`.\n"
    )
    assert parse_threshold(altered) == {
        "relative": 0.99,
        "reference": 11.0,
        "alpha": 0.30,
        "beta": 7.0,
    }
    assert parse_min_coverage(altered) == 9
    assert parse_split(altered)["control"] == (
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2020, 1, 8, tzinfo=UTC),
    )

    # And the settings must disagree with that document, which is the failure the
    # tests above would report.
    settings = Settings(_env_file=None)
    assert settings.mqo_alpha != parse_threshold(altered)["alpha"]
    assert settings.station_min_per_city_window != parse_min_coverage(altered)
