"""House-style hygiene: no em-dashes and no brand/AI-attribution tokens.

Scans every tracked text file in the repo. The forbidden tokens are assembled
from fragments at runtime and this test file excludes itself, so the scanner
never flags its own patterns. Enforces the brand-clean, em-dash-free rule across
the whole tree (not just source).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "data",
}

EM_DASH = chr(0x2014)

# Assembled from fragments so the contiguous tokens never appear literally here.
BRAND_TOKENS = [
    "co" + "-authored-by",
    "generated" + " with",
    "cl" + "aude",
    "anthro" + "pic",
    "open" + "ai",
    "cop" + "ilot",
    "chat" + "gpt",
]


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.resolve() == SELF:
                continue
            files.append(path)
    return files


def test_no_em_dashes_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if EM_DASH in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"em-dash found in: {offenders}"


def test_no_brand_tokens_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _iter_text_files():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        hits = [token for token in BRAND_TOKENS if token in text]
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {hits}")
    assert not offenders, f"brand/attribution token(s) found: {offenders}"
