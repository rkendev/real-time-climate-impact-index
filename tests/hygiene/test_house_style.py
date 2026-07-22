"""House-style hygiene: no em-dashes and no brand/AI-attribution tokens.

Scans every tracked text file in the repo, which is what the rule is actually
about: the brand-clean, em-dash-free guarantee covers what gets committed and
pushed, so the file set is exactly the one git tracks.

The file set comes from ``git ls-files`` rather than a filesystem walk. A walk
also reads untracked and ignored files, which cannot reach a commit and are
frequently not the author's at all: local editor and tool state, scratch output,
machine-local settings written by whatever runs alongside the checkout. Flagging
those reports on the working directory instead of on the repository, and it fails
red for something no commit can carry. Listing from git also means the exclusions
this used to maintain by hand (``.git``, ``.venv``, ``__pycache__``, the cache
directories, ``data``) are simply the ignore rules, with nothing to keep in sync.

Staged files are included, because ``git ls-files`` reads the index: content
added but not yet committed is exactly what this gate should catch.

The forbidden tokens are assembled from fragments at runtime and this test file
excludes itself, so the scanner never flags its own patterns.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

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


def _tracked_files() -> list[Path]:
    """Every file git tracks, plus anything staged, excluding this module.

    Uses ``-z`` so a path containing a newline or a quote is still delimited
    correctly rather than silently splitting into two entries and hiding one.
    A tracked path that has been deleted from the working tree is skipped: it is
    still in the index but there is nothing to read.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    files: list[Path] = []
    for name in listing.split("\0"):
        if not name:
            continue
        path = REPO_ROOT / name
        if not path.is_file() or path.resolve() == SELF:
            continue
        files.append(path)
    return files


def test_the_scan_covers_the_tracked_tree() -> None:
    """The two rules below pass by absence, so an empty file set would look clean.

    This pins the file set itself: the scan has to reach real repository content,
    and it must not reach a git-ignored file, which is the failure mode that made
    the walk report on the working directory rather than on the repository.
    """
    tracked = _tracked_files()
    assert len(tracked) > 50, f"suspiciously few tracked files scanned: {len(tracked)}"

    names = {path.relative_to(REPO_ROOT).as_posix() for path in tracked}
    # Content from several parts of the tree, not just one corner of it.
    assert "README.md" in names
    assert "docs/20_spec.md" in names
    assert "src/climate_index/config.py" in names

    ignored = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            "--exclude-standard",
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    ignored_names = {name for name in ignored.split("\0") if name}
    assert not (names & ignored_names), "the scan reached a git-ignored file"


def test_no_em_dashes_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if EM_DASH in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"em-dash found in: {offenders}"


def test_no_brand_tokens_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        hits = [token for token in BRAND_TOKENS if token in text]
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {hits}")
    assert not offenders, f"brand/attribution token(s) found: {offenders}"
