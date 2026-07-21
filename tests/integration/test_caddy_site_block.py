"""The demo's site block is added to an existing Caddy config without disturbing it.

The box the demo runs on already has one Caddy fronting several other sites, so
the risky part of the standup is not the demo, it is everything else on port 443.
This drives the committed ``deploy/vps/install_caddy_site.sh`` against a fixture
configuration and pins the properties that keep the other sites safe: the existing
content survives byte for byte, the block is rendered from the tracked template
with the host and port substituted, re-running replaces rather than duplicates it,
removing restores the original exactly, and a configuration that fails validation
is never installed.

The validator and the reload are substituted with stubs, so the test never touches
a running proxy.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "vps" / "install_caddy_site.sh"

DEMO_HOST = "climate-index.demo.invalid"
DEMO_PORT = "8501"

EXISTING_CONFIG = """\
:80 {
\trespond "ok" 200
}

other-site.demo.invalid {
\treverse_proxy 127.0.0.1:8001
\tencode gzip
}
"""


def _stub(path: Path, *, exit_code: int = 0) -> Path:
    """Write an executable stub that records that it ran, then exits as told."""
    marker = path.with_suffix(".ran")
    path.write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{marker}"\nexit {exit_code}\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return marker


def _run(
    tmp_path: Path,
    caddyfile: Path,
    *args: str,
    validator_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "demo.env"
    env_file.write_text(
        f"CII_DEMO_HOST={DEMO_HOST}\nCII_DEMO_PORT={DEMO_PORT}\n",
        encoding="utf-8",
    )
    validator = tmp_path / "caddy_stub"
    _stub(validator, exit_code=validator_exit)
    reload_stub = tmp_path / "reload_stub"
    _stub(reload_stub)

    environment = dict(os.environ)
    environment.update(
        {
            "CII_DEMO_ENV_FILE": str(env_file),
            "CII_DEMO_CADDYFILE": str(caddyfile),
            "CII_DEMO_CADDY_BIN": str(validator),
            "CII_DEMO_RELOAD_CMD": str(reload_stub),
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=environment,
    )


def _caddyfile(tmp_path: Path) -> Path:
    path = tmp_path / "Caddyfile"
    path.write_text(EXISTING_CONFIG, encoding="utf-8")
    return path


def test_the_block_is_appended_and_the_other_sites_survive_verbatim(tmp_path: Path) -> None:
    caddyfile = _caddyfile(tmp_path)

    result = _run(tmp_path, caddyfile)
    assert result.returncode == 0, result.stderr

    installed = caddyfile.read_text(encoding="utf-8")
    assert installed.startswith(EXISTING_CONFIG), "the existing configuration was rewritten"
    assert f"{DEMO_HOST} {{" in installed
    assert f"reverse_proxy 127.0.0.1:{DEMO_PORT}" in installed
    assert "__DEMO_HOST__" not in installed and "__PORT__" not in installed
    # The template's own explanatory header is not part of what gets installed.
    assert "rendered, never installed as-is" not in installed
    # A backup of the previous configuration is left beside it.
    assert (tmp_path / "Caddyfile.bak.climate-index").read_text(encoding="utf-8") == EXISTING_CONFIG


def test_reinstalling_replaces_the_block_instead_of_duplicating_it(tmp_path: Path) -> None:
    caddyfile = _caddyfile(tmp_path)

    assert _run(tmp_path, caddyfile).returncode == 0
    once = caddyfile.read_text(encoding="utf-8")
    assert _run(tmp_path, caddyfile).returncode == 0
    twice = caddyfile.read_text(encoding="utf-8")

    assert once == twice
    assert twice.count(f"{DEMO_HOST} {{") == 1


def test_removing_restores_the_original_configuration_exactly(tmp_path: Path) -> None:
    caddyfile = _caddyfile(tmp_path)

    assert _run(tmp_path, caddyfile).returncode == 0
    assert _run(tmp_path, caddyfile, "--remove").returncode == 0

    assert caddyfile.read_text(encoding="utf-8") == EXISTING_CONFIG


def test_a_configuration_that_fails_validation_is_never_installed(tmp_path: Path) -> None:
    caddyfile = _caddyfile(tmp_path)

    result = _run(tmp_path, caddyfile, validator_exit=1)

    assert result.returncode == 1
    assert caddyfile.read_text(encoding="utf-8") == EXISTING_CONFIG
    assert "nothing was changed" in result.stderr


def test_the_configuration_is_validated_and_reloaded(tmp_path: Path) -> None:
    caddyfile = _caddyfile(tmp_path)

    assert _run(tmp_path, caddyfile).returncode == 0

    assert (tmp_path / "caddy_stub.ran").exists(), "the configuration was not validated"
    assert (tmp_path / "reload_stub.ran").exists(), "caddy was not reloaded"
