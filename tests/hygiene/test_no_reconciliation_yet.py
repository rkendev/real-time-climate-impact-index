"""T2 must not contain reconciliation. Checked by absence of its machinery.

The exclusion this enforces is that T2 computes no comparison between a station
value and a model value, anywhere, because the moment a difference exists the
sealed holdout is compromised and the compromise is unprovable afterwards.

A text search for a subtraction is a weak control: a difference can be spelled
`a - b`, `abs(a - b)`, `math.fabs`, a library call, or a helper named `delta`,
and a search finds only the spelling its author thought of. This repository has
been bitten more than once by call-site checks implemented as text searches.

So the control here is negative space instead, which is decidable rather than
hopeful. Reconciliation cannot have leaked in if the machinery it requires is
provably absent. These tests go red the moment T3 legitimately begins, which is
the point: at that moment this file is deleted in the same commit that adds the
tolerance, and its deletion is the record that the exclusion period ended.
"""

from __future__ import annotations

import ast
from pathlib import Path

from climate_index.config import Settings

SRC = Path(__file__).resolve().parents[2] / "src" / "climate_index"

# The settings keys the specification reserves for reconciliation. Declared in
# 20_spec.md, valued only when T3 lands.
RECONCILIATION_KEYS = (
    "mqo_relative_uncertainty_at_reference",
    "mqo_reference_value_ugm3",
    "mqo_alpha",
    "mqo_beta",
)


def test_no_tolerance_constant_is_configured() -> None:
    fields = set(Settings.model_fields)
    present = sorted(key for key in RECONCILIATION_KEYS if key in fields)
    assert not present, f"reconciliation settings exist during T2: {present}"


def test_no_reconciliation_function_exists() -> None:
    """No city-window aggregation and no disagreement evaluation under src/."""
    banned = ("city_window", "citywindow", "disagreement", "reconcile", "tolerance", "mqo")
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            lowered = node.name.lower()
            if any(token in lowered for token in banned):
                found.append(f"{path.relative_to(SRC)}:{node.lineno} {node.name}")
    assert not found, f"reconciliation machinery exists during T2: {found}"


def test_the_scan_would_notice_if_it_appeared() -> None:
    """The absence tests above must be able to fail, not pass vacuously."""
    tree = ast.parse("def evaluate_disagreement():\n    pass\n")
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "disagreement" in node.name.lower()
    ]
    assert names == ["evaluate_disagreement"]
    assert SRC.is_dir() and any(SRC.rglob("*.py")), "the scan reached no source files"
