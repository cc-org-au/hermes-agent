from agent.openai_primary_mode import (
    opm_suppresses_free_model_fallback,
    resolve_openai_primary_mode,
)


def test_opm_suppresses_free_model_fallback_true_when_enabled_and_native(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": True}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "k"),
    )
    assert opm_suppresses_free_model_fallback() is True


def test_opm_suppresses_free_model_fallback_false_without_native(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": True}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: None,
    )
    assert opm_suppresses_free_model_fallback() is False


def test_opm_suppresses_merges_parent_governance_cache(monkeypatch):
    """``opm_suppresses_free_model_fallback(agent)`` must see parent's runtime OPM flags."""
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": False}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "k"),
    )

    class _P:
        _token_governance_cfg = {"openai_primary_mode": {"enabled": True}}

    assert opm_suppresses_free_model_fallback(_P()) is True


def test_opm_precedence_parent_over_runtime_over_config(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": False,
                "default_model": "cfg-default",
                "codex_model": "cfg-codex",
            }
        },
    )
    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "default_model": "rt-default",
            }
        },
    )
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: ("https://api.openai.com/v1", "key"),
    )

    class _Parent:
        _token_governance_cfg = {
            "openai_primary_mode": {
                "enabled": True,
                "default_model": "parent-default",
            }
        }

    opm, meta = resolve_openai_primary_mode(_Parent())
    assert opm["enabled"] is True
    assert opm["default_model"] == "parent-default"
    # Field-level merge should preserve codex model from lower layers.
    assert opm["codex_model"] == "cfg-codex"
    assert meta["source"] == "parent_cached"


def test_opm_runtime_overrides_config_field_by_field(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": True,
                "default_model": "cfg-default",
                "codex_model": "cfg-codex",
                "require_direct_openai": True,
            }
        },
    )
    monkeypatch.setattr(
        "agent.token_governance_runtime.load_runtime_config",
        lambda: {
            "openai_primary_mode": {
                "enabled": False,
                "default_model": "rt-default",
            }
        },
    )
    monkeypatch.setattr(
        "agent.openai_native_runtime.native_openai_runtime_tuple",
        lambda: None,
    )

    opm, meta = resolve_openai_primary_mode(None)
    assert opm["enabled"] is False
    assert opm["default_model"] == "rt-default"
    # Unspecified runtime fields keep config values.
    assert opm["codex_model"] == "cfg-codex"
    assert opm["require_direct_openai"] is True
    assert meta["source"] == "runtime_yaml"
    assert meta["has_native_openai_runtime"] is False

