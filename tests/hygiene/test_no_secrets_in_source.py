"""INV-1 / NFR-SEC1: no secret or endpoint literal appears in source.

Greps every Python module under src/ for endpoint and credential patterns. All
connection details come from the config object populated by the environment;
example values live only in .env.example (which is not source and is excluded).
The patterns target literal values (URLs, host:port, access keys, embedded
credentials), not identifiers, so config field names do not false-positive.

One narrow allowance: a public source-repository link on a source-hosting domain
is neither a credential nor a service endpoint the code connects to. The
dashboard renders the project's repository URL as a link (UC-5) and the code
never dials it, so a match on that prefix is not a finding. Every other pattern,
including credentials embedded in a URL, still applies to it.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src"

# Public documentation links that the code renders but never connects to. Only
# the "url with scheme" pattern honours this allowance.
PUBLIC_URL_PREFIXES = ("https://github.com/",)

FORBIDDEN = [
    # The whole URL is captured (not just its first character) so a match can be
    # weighed against the public-link allowance below.
    ("url with scheme", re.compile(r"\b(?:https?|kafka|redis|postgres(?:ql)?)://\S+", re.I)),
    ("credentials in url", re.compile(r"://[^/\s]+:[^/@\s]+@")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("ipv4 host:port", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b")),
    ("localhost endpoint", re.compile(r"\blocalhost:\d{2,5}\b", re.I)),
    (
        "secret assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|"
            r"aws_secret_access_key)\b\s*[:=]\s*['\"][^'\"]+['\"]"
        ),
    ),
]


def _is_allowed(label: str, hit: str) -> bool:
    """True for a public documentation link the code renders but never dials."""
    return label == "url with scheme" and hit.startswith(PUBLIC_URL_PREFIXES)


def test_source_has_no_secret_or_endpoint_literals() -> None:
    assert SRC_DIR.is_dir(), f"src not found at {SRC_DIR}"
    findings: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                hit = match.group(0)
                if _is_allowed(label, hit):
                    continue
                findings.append(f"{path}: {label}: {hit!r}")
                break
    assert not findings, "secret/endpoint literal(s) in source (INV-1): " + "; ".join(findings)


def test_the_public_link_allowance_is_narrow() -> None:
    """The allowance covers a bare public repository link and nothing else."""
    assert _is_allowed("url with scheme", "https://github.com/owner/repo")
    assert not _is_allowed("url with scheme", "https://example.invalid/service")
    assert not _is_allowed("credentials in url", "https://github.com/owner/repo")
    # A credential smuggled into an allowed host is still caught: the allowance
    # is per-pattern, and the credentials pattern does not honour it.
    credentials = dict(FORBIDDEN)["credentials in url"]
    assert credentials.search("https://user:secretvalue@github.com/owner/repo")
