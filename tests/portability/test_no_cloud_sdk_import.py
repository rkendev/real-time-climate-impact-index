"""Core portability: no vendor SDK (INV-4, AT-10) and no network client (INV-6).

Walks every module under src/climate_index/core/ and parses its imports with the
AST, then applies two denylists to what it finds.

INV-4 / AT-10 bans cloud-vendor SDKs and transport clients. It passed trivially
in Phase 1 (core was empty of logic) and guards the AWS phase: all vendor
specifics must live behind the transport and store adapters.

INV-6 (ADR-0007) bans network clients outright. INV-4 says nothing about plain
HTTP, and once the project fetches real readings that gap matters: every
external data source must sit behind a source adapter selected by config, so the
core stays pure, offline, and unit-testable with no network and no credentials.
Both use the same walk, so a module cannot satisfy one check and dodge the other.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "src" / "climate_index" / "core"

# Top-level module names that must never be imported under core/.
DENYLIST = {
    "boto3",
    "botocore",
    "aws",
    "awscli",
    "kafka",
    "confluent_kafka",
    "aiokafka",
}

# Network clients that must never be imported under core/ (INV-6, ADR-0007).
# Listed by top-level module because that is the granularity the AST walk
# reports: "urllib" covers urllib.request, which is the one that dials.
NETWORK_DENYLIST = {
    "httpx",
    "requests",
    "urllib",
    "aiohttp",
    "socket",
    "http",
    "urllib3",
}


def _top_level(name: str) -> str:
    return name.split(".", 1)[0]


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(_top_level(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(_top_level(node.module))
    return modules


def _offenders_against(denylist: set[str]) -> dict[str, set[str]]:
    """Map each core module to the denylisted top-level modules it imports."""
    assert CORE_DIR.is_dir(), f"core package not found at {CORE_DIR}"
    offenders: dict[str, set[str]] = {}
    for path in sorted(CORE_DIR.rglob("*.py")):
        banned = _imported_modules(path.read_text(encoding="utf-8")) & denylist
        if banned:
            offenders[str(path)] = banned
    return offenders


def test_core_imports_no_cloud_sdk() -> None:
    offenders = _offenders_against(DENYLIST)
    assert not offenders, f"cloud SDK imports found under core/ (INV-4): {offenders}"


def test_core_imports_no_network_client() -> None:
    """INV-6: every external data source sits behind a source adapter."""
    offenders = _offenders_against(NETWORK_DENYLIST)
    assert not offenders, f"network client imports found under core/ (INV-6): {offenders}"


def test_the_walk_actually_detects_a_banned_import() -> None:
    """The denylists are only worth having if the walk they feed can fail.

    Both invariants pass by absence, so a broken parse or an empty walk would
    look identical to a clean core. This pins the mechanism itself against a
    sample of each denylist rather than trusting a green result.
    """
    assert _imported_modules("import httpx") == {"httpx"}
    assert _imported_modules("from urllib.request import urlopen") == {"urllib"}
    assert _imported_modules("import boto3") & DENYLIST
    assert _imported_modules("import httpx") & NETWORK_DENYLIST
    assert not _imported_modules("from datetime import UTC") & NETWORK_DENYLIST
