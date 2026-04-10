"""Syntax-check optional shell watchdog scripts (no runtime execution)."""

import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = [
    _REPO / "scripts/core/droplet_pull_hermes_home.sh",
    _REPO / "scripts/core/gateway-watchdog.sh",
    _REPO / "scripts/core/install_and_restart_gateway_watchdog.sh",
]


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.name)
def test_gateway_watchdog_scripts_bash_syntax(path: Path) -> None:
    assert path.is_file(), f"missing {path}"
    subprocess.run(["bash", "-n", str(path)], check=True)
