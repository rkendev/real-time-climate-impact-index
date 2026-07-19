"""INV-1 / NFR-SEC1: no secret or endpoint literal appears in source.

Greps every Python module under src/ for endpoint and credential patterns. All
connection details come from the config object populated by the environment;
example values live only in .env.example (which is not source and is excluded).
The patterns target literal values (URLs, host:port, access keys, embedded
credentials), not identifiers, so config field names do not false-positive.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src"

FORBIDDEN = [
    ("url with scheme", re.compile(r"\b(?:https?|kafka|redis|postgres(?:ql)?)://\S", re.I)),
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


def test_source_has_no_secret_or_endpoint_literals() -> None:
    assert SRC_DIR.is_dir(), f"src not found at {SRC_DIR}"
    findings: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN:
            match = pattern.search(text)
            if match:
                findings.append(f"{path}: {label}: {match.group(0)!r}")
    assert not findings, "secret/endpoint literal(s) in source (INV-1): " + "; ".join(findings)
