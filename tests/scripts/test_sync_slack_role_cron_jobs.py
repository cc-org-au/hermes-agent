"""sync_slack_role_cron_jobs.py hermes-hop inference and prompt suffix."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "memory" / "core" / "scripts" / "core" / "sync_slack_role_cron_jobs.py"


def _load_sync_mod():
    spec = importlib.util.spec_from_file_location("sync_slack_role_cron_jobs", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_script_exists() -> None:
    assert _SCRIPT.is_file(), f"missing {_SCRIPT}"


@pytest.mark.parametrize(
    ("profile", "cfg", "want"),
    [
        ("chief-orchestrator", {}, "--operator"),
        ("chief-orchestrator-droplet", {}, "--operator"),
        (
            "chief-orchestrator",
            {"messaging": {"role_routing": {"slack": {"hermes_hop": "droplet"}}}},
            "--droplet",
        ),
        (
            "chief-orchestrator-droplet",
            {"messaging": {"role_routing": {"slack": {"hermes_hop": "operator"}}}},
            "--operator",
        ),
    ],
)
def test_infer_hermes_hop_tag(
    profile: str,
    cfg: dict,
    want: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HERMES_SLACK_ROLE_HERMES_HOP", raising=False)
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / profile
    home.mkdir(parents=True)
    assert mod._infer_hermes_hop_tag(home, cfg) == want


def test_infer_hermes_hop_env_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_SLACK_ROLE_HERMES_HOP", "droplet")
    assert mod._infer_hermes_hop_tag(home, {}) == "--droplet"


def test_resolve_explicit_hermes_hop(tmp_path: Path) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    assert (
        mod._resolve_hermes_hop_tag(hermes_hop="droplet", chief_tag=None, home=home, cfg={})
        == "--droplet"
    )


def test_resolve_legacy_chief_tag_strips_profile_name(tmp_path: Path) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator-droplet"
    home.mkdir(parents=True)
    assert (
        mod._resolve_hermes_hop_tag(
            hermes_hop="auto",
            chief_tag="--operator --chief-orchestrator",
            home=home,
            cfg={},
        )
        == "--operator"
    )


def test_effective_slack_overlay_replaces_base_channels(tmp_path: Path) -> None:
    """Overlay ``slack.channels`` replaces the base map entirely (gateway merge semantics)."""
    mod = _load_sync_mod()
    prof = tmp_path / "profiles" / "p1"
    prof.mkdir(parents=True)
    (prof / "config.yaml").write_text(
        "messaging:\n  role_routing:\n    slack:\n      channels:\n        C1: only-base\n",
        encoding="utf-8",
    )
    ops = prof / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    (ops / "messaging_role_routing.yaml").write_text(
        "slack:\n  channels:\n    C2: from-overlay\n",
        encoding="utf-8",
    )
    cfg = {"messaging": {"role_routing": {"slack": {"channels": {"C1": "only-base"}}}}}
    ch = mod._effective_slack_role_channels(prof, cfg)
    assert ch == {"C2": "from-overlay"}


def test_role_prompt_uses_hop_and_slug() -> None:
    mod = _load_sync_mod()
    text = mod._role_prompt("org-mapper-hr-controller", "C0123", hermes_hop_tag="--droplet")
    assert text.endswith(
        "Append its own final line exactly: `--droplet --org-mapper-hr-controller` "
        "(Hermes hop from this host, then the role slug from config — not the orchestrator profile name)."
    )
