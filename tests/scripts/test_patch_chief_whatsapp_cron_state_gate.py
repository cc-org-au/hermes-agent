from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "memory" / "core" / "scripts" / "core" / "patch_chief_whatsapp_cron_state_gate.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("patch_chief_whatsapp_cron_state_gate", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_script_exists() -> None:
    assert _SCRIPT.is_file()


def test_infer_hermes_hop_from_env_file(tmp_path: Path, monkeypatch) -> None:
    mod = _load_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    home.mkdir(parents=True)
    (home / ".env").write_text("HERMES_GATEWAY_LOCK_INSTANCE=droplet\n", encoding="utf-8")
    monkeypatch.delenv("HERMES_SLACK_ROLE_HERMES_HOP", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_LOCK_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_CLI_INSTANCE_LABEL", raising=False)
    assert mod._infer_hermes_hop_tag(home) == "--droplet"


def test_apply_updates_current_whatsapp_jobs(tmp_path: Path, monkeypatch) -> None:
    mod = _load_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    cron_dir = home / "cron"
    cron_dir.mkdir(parents=True)
    (home / ".env").write_text("HERMES_GATEWAY_LOCK_INSTANCE=droplet\n", encoding="utf-8")

    jobs = {
        "jobs": [
            {
                "id": "6bc442ae2aec",
                "name": "whatsapp-gateway-connectivity-alerts",
                "prompt": "Use state from /home/hermesuser/.hermes/cron-state/whatsapp-gateway-watchdog/state.json",
                "deliver": "whatsapp:61483757391",
                "model": "openai/gpt-5.4-nano",
                "provider": "openrouter",
            },
            {
                "id": "cd38fdfdc932",
                "name": "hourly-whatsapp-human-operator-escalation",
                "prompt": (
                    "Some text.\n\n"
                    "Append a final line containing exactly: --operator --chief-orchestrator\n"
                    "(Place it on its own line after the message content.)"
                ),
                "deliver": "whatsapp:61483757391",
                "model": "something-else",
                "provider": "other",
            },
        ]
    }
    jobs_path = cron_dir / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    assert mod.main() == 0

    data = json.loads(jobs_path.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in data["jobs"]}

    gate = rows["6bc442ae2aec"]["state_skip_gate"]
    assert gate["path"].endswith("/.hermes/cron-state/whatsapp-gateway-watchdog/state.json")
    assert gate["keys"] == ["last_status_key", "connected_platforms"]
    assert rows["6bc442ae2aec"]["model"] == "openrouter/free"
    assert rows["6bc442ae2aec"]["provider"] == "openrouter"
    assert "--droplet --chief-orchestrator" in rows["6bc442ae2aec"]["prompt"]

    escalation_gate = rows["cd38fdfdc932"]["state_skip_gate"]
    assert escalation_gate["path"].endswith("/.hermes/cron-state/hourly-whatsapp-human-operator-escalation/state.json")
    assert escalation_gate["keys"] == ["last_status_key"]
    assert rows["cd38fdfdc932"]["model"] == "openrouter/free"
    assert rows["cd38fdfdc932"]["provider"] == "openrouter"
    assert "--droplet --chief-orchestrator" in rows["cd38fdfdc932"]["prompt"]
    assert "--operator --chief-orchestrator" not in rows["cd38fdfdc932"]["prompt"]


def test_dry_run_is_idempotent_for_current_format(tmp_path: Path, monkeypatch, capsys) -> None:
    mod = _load_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    cron_dir = home / "cron"
    cron_dir.mkdir(parents=True)
    (home / ".env").write_text("HERMES_GATEWAY_LOCK_INSTANCE=droplet\n", encoding="utf-8")

    jobs = {
        "jobs": [
            {
                "id": "6bc442ae2aec",
                "name": "whatsapp-gateway-connectivity-alerts",
                "prompt": (
                    "Use state from /tmp/ok\n\n"
                    "Return only the policy lines.\n"
                    "The final line must be exactly --droplet --chief-orchestrator on its own line."
                ),
                "deliver": "whatsapp:61483757391",
                "model": "openrouter/free",
                "provider": "openrouter",
                "state_skip_gate": {
                    "path": str(home.parent.parent / "cron-state" / "whatsapp-gateway-watchdog" / "state.json"),
                    "keys": ["last_status_key", "connected_platforms"],
                },
            }
        ]
    }
    jobs_path = cron_dir / "jobs.json"
    original = json.dumps(jobs, indent=2) + "\n"
    jobs_path.write_text(original, encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sys, "argv", ["x"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "No changes needed." in out
    assert jobs_path.read_text(encoding="utf-8") == original
