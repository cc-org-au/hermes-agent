"""normalize_cron_jobs_policy.py profile-tree normalization."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "memory" / "core" / "scripts" / "core" / "normalize_cron_jobs_policy.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("normalize_cron_jobs_policy", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_script_exists() -> None:
    assert _SCRIPT.is_file(), f"missing {_SCRIPT}"


def test_iter_target_homes_includes_root_and_profiles(tmp_path: Path) -> None:
    mod = _load_mod()
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "profiles" / "chief-orchestrator").mkdir(parents=True)
    (root / "profiles" / "chief-orchestrator-droplet").mkdir(parents=True)

    homes = mod.iter_target_homes(root / "profiles" / "chief-orchestrator", all_profiles=True)
    assert root in homes
    assert root / "profiles" / "chief-orchestrator" in homes
    assert root / "profiles" / "chief-orchestrator-droplet" in homes


def test_normalize_home_updates_config_and_jobs(tmp_path: Path) -> None:
    mod = _load_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    (home / "cron").mkdir(parents=True)
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "cron": {
                    "default_model": "openai/gpt-4o-mini",
                    "default_provider": "gemini",
                    "strict_delivery_envelope": False,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (home / "cron" / "jobs.json").write_text(
        json.dumps(
            [
                {
                    "id": "j1",
                    "name": "nightly",
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "provider": "gemini",
                    "base_url": "https://example.invalid/v1",
                    "strict_delivery_envelope": False,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = mod.normalize_home(home, apply=True)
    assert result["config_changed"] is True
    assert result["jobs_changed"] is True
    assert result["updated_jobs"] == 1

    cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["cron"]["default_model"] == "openrouter/free"
    assert cfg["cron"]["default_provider"] == "openrouter"
    assert cfg["cron"]["strict_delivery_envelope"] is True

    jobs = json.loads((home / "cron" / "jobs.json").read_text(encoding="utf-8"))
    assert jobs[0]["model"] == "openrouter/free"
    assert jobs[0]["provider"] == "openrouter"
    assert jobs[0]["strict_delivery_envelope"] is True
    assert jobs[0]["base_url"] is None


def test_normalize_home_preserves_wrapped_jobs_payload(tmp_path: Path) -> None:
    mod = _load_mod()
    home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    (home / "cron").mkdir(parents=True)
    (home / "cron" / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "j1",
                        "name": "nightly",
                        "model": "meta-llama/llama-3.3-70b-instruct:free",
                        "provider": "gemini",
                        "strict_delivery_envelope": False,
                    }
                ],
                "updated_at": "2026-04-14T00:00:00+00:00",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = mod.normalize_home(home, apply=True)
    assert result["jobs_changed"] is True
    payload = json.loads((home / "cron" / "jobs.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["updated_at"] == "2026-04-14T00:00:00+00:00"
    assert payload["jobs"][0]["model"] == "openrouter/free"
    assert payload["jobs"][0]["provider"] == "openrouter"
