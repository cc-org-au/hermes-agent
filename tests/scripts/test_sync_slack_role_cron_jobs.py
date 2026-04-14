"""sync_slack_role_cron_jobs.py hermes-hop inference and role-specific suffix."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

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
        ("chief-orchestrator-droplet", {}, "--droplet"),
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


def test_infer_hermes_hop_gateway_lock_instance_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    monkeypatch.delenv("HERMES_SLACK_ROLE_HERMES_HOP", raising=False)
    monkeypatch.setenv("HERMES_GATEWAY_LOCK_INSTANCE", "droplet")
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


def test_role_prompt_uses_hop_and_role_suffix() -> None:
    mod = _load_sync_mod()
    text = mod._role_prompt(
        "org-mapper-hr-controller",
        "C0123",
        hermes_hop_tag="--droplet",
    )
    assert "Add the final line in the JSON `lines` array exactly: `--droplet --org-mapper-hr-controller`" in text
    assert "###HERMES_CRON_DELIVERY_JSON" in text
    assert "requested decision, if any:" in text
    assert "Slack is **never** a human-operator intervention channel." in text


def test_expand_role_slugs_for_executive_briefings() -> None:
    mod = _load_sync_mod()
    assert mod._expand_role_slugs("executive-team-briefings") == (
        "project-lead-agentic-company",
        "engineering-director",
        "it-security-director",
        "operations-director",
        "product-director",
    )


def test_refresh_role_slug_for_multi_role_channel_uses_job_name() -> None:
    mod = _load_sync_mod()
    job = {"name": "daily-slack-role-status-product-director-C0EXEC"}
    assert (
        mod._refresh_role_slug_for_job(job, "executive-team-briefings", "C0EXEC")
        == "product-director"
    )


def test_apply_creates_slack_role_job_with_strict_delivery_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator-droplet"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        "cron:\n"
        "  default_model: openai/gpt-4o-mini\n"
        "  default_provider: openrouter\n"
        "messaging:\n"
        "  role_routing:\n"
        "    slack:\n"
        "      channels:\n"
        "        C1: org-mapper-hr-controller\n",
        encoding="utf-8",
    )
    captured: dict = {}

    def _save_jobs(rows):
        captured["jobs"] = rows

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    with patch("cron.jobs.load_jobs", return_value=[]), patch(
        "cron.jobs.compute_next_run", return_value="2026-01-01T00:00:00+00:00"
    ), patch("cron.jobs.save_jobs", side_effect=_save_jobs):
        assert mod.main() == 0
    jobs = captured["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["strict_delivery_envelope"] is True
    assert jobs[0]["model"] == "openai/gpt-4o-mini"
    assert jobs[0]["provider"] == "openrouter"


def test_apply_creates_multiple_exec_jobs_for_executive_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        "cron:\n"
        "  default_model: openrouter/free\n"
        "  default_provider: openrouter\n"
        "messaging:\n"
        "  role_routing:\n"
        "    slack:\n"
        "      channels:\n"
        "        CEXEC: executive-team-briefings\n",
        encoding="utf-8",
    )
    captured: dict = {}

    def _save_jobs(rows):
        captured["jobs"] = rows

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    with patch("cron.jobs.load_jobs", return_value=[]), patch(
        "cron.jobs.compute_next_run", return_value="2026-01-01T00:00:00+00:00"
    ), patch("cron.jobs.save_jobs", side_effect=_save_jobs):
        assert mod.main() == 0
    names = [job["name"] for job in captured["jobs"]]
    assert names == [
        "daily-slack-role-status-project-lead-agentic-company-CEXEC",
        "daily-slack-role-status-engineering-director-CEXEC",
        "daily-slack-role-status-it-security-director-CEXEC",
        "daily-slack-role-status-operations-director-CEXEC",
        "daily-slack-role-status-product-director-CEXEC",
    ]


def test_apply_skips_standalone_project_lead_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_sync_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        "cron:\n"
        "  default_model: openrouter/free\n"
        "  default_provider: openrouter\n"
        "messaging:\n"
        "  role_routing:\n"
        "    slack:\n"
        "      channels:\n"
        "        CPROJ: project-lead-agentic-company\n",
        encoding="utf-8",
    )
    captured: dict = {}

    def _save_jobs(rows):
        captured["jobs"] = rows

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    with patch("cron.jobs.load_jobs", return_value=[]), patch(
        "cron.jobs.compute_next_run", return_value="2026-01-01T00:00:00+00:00"
    ), patch("cron.jobs.save_jobs", side_effect=_save_jobs):
        assert mod.main() == 0
    assert captured["jobs"] == []
