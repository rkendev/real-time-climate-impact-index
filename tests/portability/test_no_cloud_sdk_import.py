"""AT-10 / INV-4: no cloud-vendor SDK import appears under the core package.

Walks every module under src/climate_index/core/ and parses its imports with the
AST. Fails if any module imports a denylisted cloud SDK or transport client.
Passes trivially in Phase 1 (core is empty of logic) and guards the AWS phase:
all vendor specifics must live behind the transport and store adapters.
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


def test_core_imports_no_cloud_sdk() -> None:
    assert CORE_DIR.is_dir(), f"core package not found at {CORE_DIR}"
    offenders: dict[str, set[str]] = {}
    for path in sorted(CORE_DIR.rglob("*.py")):
        banned = _imported_modules(path.read_text(encoding="utf-8")) & DENYLIST
        if banned:
            offenders[str(path)] = banned
    assert not offenders, f"cloud SDK imports found under core/ (INV-4): {offenders}"
