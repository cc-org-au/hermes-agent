from types import SimpleNamespace

from agent.disallowed_model_family import model_id_contains_disallowed_family


def test_default_free_subprocess_model_never_disallowed_family_when_opm_enabled(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "allowed_subprocess_models": ["gpt-5.4"],
                "default_model": "gpt-5.4",
            },
            "free_model_routing": {"gemini_native_tier_models": ["gemini-2.5-flash"]},
        },
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    mid = sg.default_free_subprocess_model_id(None)
    assert not model_id_contains_disallowed_family(mid)
    assert mid == "gpt-5.4"


def test_openai_primary_mode_allows_runtime_yaml_config(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
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
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: None,
    )
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


def test_openai_primary_mode_allows_other_gpt_slugs_when_opm_native_available(monkeypatch):
    """Any ``gpt-*`` OpenAI API slug is allowed under OPM when keys exist (not only E/F consultants)."""
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "allowed_subprocess_models": [],
                "require_direct_openai": True,
            }
        },
    )
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
        _delegate_launch_hermes_home=None,
    )
    assert sg._is_openai_primary_mode_allowed("gpt-4.1", parent) is True
    assert sg._is_openai_primary_mode_allowed("openai/gpt-4o-mini", parent) is True


def test_openai_primary_mode_accepts_openai_prefixed_model_id(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
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
    assert sg._is_openai_primary_mode_allowed("openai/gpt-5.4", parent) is True


def test_openai_primary_mode_rejects_custom_non_openai_base(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: None,
    )
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

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="custom",
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is False


def test_openai_primary_mode_subprocess_pins_chief_hermes_home_under_profile_env(
    monkeypatch, tmp_path,
):
    """delegate_task(hermes_profile=…) sets process HERMES_HOME to the child profile; OPM for the
    subprocess gate must still read the session chief's config.yaml."""
    from agent import subprocess_governance as sg

    chief_home = tmp_path / "chief"
    child_home = tmp_path / "project-lead"
    chief_home.mkdir()
    child_home.mkdir()
    (chief_home / "config.yaml").write_text(
        "openai_primary_mode:\n"
        "  enabled: true\n"
        "  allowed_subprocess_models: [gpt-5.4]\n"
        "  require_direct_openai: true\n",
        encoding="utf-8",
    )
    (child_home / "config.yaml").write_text(
        "openai_primary_mode:\n  enabled: false\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(child_home))
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
        _delegate_launch_hermes_home=str(chief_home),
        _token_governance_cfg=None,
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is True

    parent_no_pin = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
        _token_governance_cfg=None,
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent_no_pin) is False


def test_openai_primary_mode_loads_profile_dotenv_before_native_openai_check(
    monkeypatch, tmp_path
):
    """Subprocess gate must see OPENAI_* from ``HERMES_HOME/.env`` even when unset in shell."""
    from agent import subprocess_governance as sg

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / ".env").write_text("OPENAI_API_KEY=sk-test-from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_DROPLET", raising=False)

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

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is True
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_openai_primary_mode_empty_allowed_list_uses_default_and_primary_models(monkeypatch):
    """Merged YAML can yield ``allowed_subprocess_models: []``; OPM should still allow primaries."""
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "allowed_subprocess_models": [],
                "default_model": "gpt-5.4",
                "require_direct_openai": True,
            }
        },
    )
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is True
    assert sg._is_openai_primary_mode_allowed("gpt-5.3-codex", parent) is True


def test_openai_primary_mode_allows_gemini_parent_when_openai_runtime_available(monkeypatch):
    from agent import subprocess_governance as sg

    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )
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

    parent = SimpleNamespace(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        provider="gemini",
    )
    assert sg._is_openai_primary_mode_allowed("gpt-5.4", parent) is True
