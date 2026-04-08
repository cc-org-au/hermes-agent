from types import SimpleNamespace


def test_openai_primary_mode_allows_runtime_yaml_config(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "allowed_subprocess_models": ["gpt-5.4", "gpt-5.3-codex"],
                "require_direct_openai": True,
            }
        },
    )
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})

    parent = SimpleNamespace(base_url="https://api.openai.com/v1", provider="custom")
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is True


def test_openai_primary_mode_rejects_openrouter_parent(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "allowed_subprocess_models": ["gpt-5.4", "gpt-5.3-codex"],
                "require_direct_openai": True,
            }
        },
    )
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})

    parent = SimpleNamespace(base_url="https://openrouter.ai/api/v1", provider="openrouter")
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is False
