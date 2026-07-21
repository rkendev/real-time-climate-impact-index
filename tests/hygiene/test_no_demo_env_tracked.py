"""INV-1: the live demo tracks placeholders only, never a host-specific value.

The demo under deploy/vps/ is deployed by rendering tracked templates against a
git-ignored demo.env holding the real public host. This turns that split into a
checked invariant, the same way test_no_tfvars_tracked.py does for the terraform
variables: no real *.env may be tracked, and no tracked file under deploy/ may
carry a literal IPv4 address or a resolved sslip.io host name.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# A dotted IPv4 literal, and the dashed form a resolved sslip.io host would carry.
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
SSLIP_HOST = re.compile(r"\b\d{1,3}(?:-\d{1,3}){3}\.sslip\.io\b")

# Loopback and the unspecified address are structural, not host-specific: the
# dashboard binds loopback and Caddy proxies to it, on every box alike.
ALLOWED_ADDRESSES = {"127.0.0.1", "0.0.0.0"}


def _tracked_deploy_files() -> list[str]:
    return subprocess.run(
        ["git", "ls-files", "deploy"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def test_no_real_demo_env_is_tracked() -> None:
    offenders = [
        path
        for path in _tracked_deploy_files()
        if path.endswith(".env") and not path.endswith(".env.example")
    ]
    assert not offenders, f"real demo .env tracked (must be git-ignored, INV-1): {offenders}"


def test_no_host_literal_in_tracked_deploy_files() -> None:
    findings: list[str] = []
    for path in _tracked_deploy_files():
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        for address in IPV4.findall(text):
            if address not in ALLOWED_ADDRESSES:
                findings.append(f"{path}: ipv4 literal: {address!r}")
        host = SSLIP_HOST.search(text)
        if host:
            findings.append(f"{path}: resolved demo host: {host.group(0)!r}")
    assert not findings, "host-specific literal in a tracked deploy file (INV-1): " + "; ".join(
        findings
    )
