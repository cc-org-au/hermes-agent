from unittest.mock import MagicMock

from agent.openai_primary_mode import (
    _opm_merge_parent_anchor,
    coerce_model_off_gemma_under_opm,
    coerce_opm_disallowed_routing_slugs,
    filter_fallback_chain_strip_gemma,
    is_gemma_model_id,
    is_opm_blocked_openrouter_auto_slug,
    opm_blocks_gemma,
    opm_suppresses_free_model_fallback,
    resolve_openai_primary_mode,
)


def test_opm_merge_parent_anchor_magicmock_unset_is_none():
    """MagicMock.__getattr__ must not fabricate a delegation anchor."""
    assert _opm_merge_parent_anchor(MagicMock()) is None


def test_opm_merge_parent_anchor_explicit_on_mock():
    chief = object()
    m = MagicMock()
    m._opm_merge_parent = chief
    assert _opm_merge_parent_anchor(m) is chief


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


def test_is_gemma_model_id():
    assert is_gemma_model_id("gemma-4-31b-it")
    assert is_gemma_model_id("google/gemma-4-31b-it")
    assert not is_gemma_model_id("google/gemini-2.5-flash")
    assert not is_gemma_model_id("")


def test_coerce_model_off_gemma_when_opm_enabled(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": True, "default_model": "gpt-5.4"}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert coerce_model_off_gemma_under_opm("gemma-4-31b-it", None) == "gpt-5.4"
    assert coerce_model_off_gemma_under_opm("gpt-5.4", None) == "gpt-5.4"


def test_coerce_model_passthrough_when_opm_disabled(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": False}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert coerce_model_off_gemma_under_opm("gemma-4-31b-it", None) == "gemma-4-31b-it"


def test_opm_blocks_gemma_follows_enabled_flag(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": True}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert opm_blocks_gemma() is True

    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": False}},
    )
    assert opm_blocks_gemma() is False


def test_opm_blocks_gemma_truthy_string_enabled(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": "true"}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert opm_blocks_gemma() is True


def test_is_opm_blocked_openrouter_auto_slug():
    assert is_opm_blocked_openrouter_auto_slug("openrouter/auto")
    assert is_opm_blocked_openrouter_auto_slug("openrouter-auto")
    assert is_opm_blocked_openrouter_auto_slug("OpenRouter_Auto")
    assert not is_opm_blocked_openrouter_auto_slug("openai/gpt-5.4")


def test_coerce_opm_disallowed_openrouter_auto(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": True, "default_model": "gpt-5.4"}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert coerce_opm_disallowed_routing_slugs("openrouter/auto", None) == "gpt-5.4"


def test_coerce_opm_passthrough_auto_when_opm_off(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"openai_primary_mode": {"enabled": False}},
    )
    monkeypatch.setattr("agent.token_governance_runtime.load_runtime_config", lambda: {})
    assert coerce_opm_disallowed_routing_slugs("openrouter/auto", None) == "openrouter/auto"


def test_filter_fallback_chain_strip_gemma():
    chain = [
        {"provider": "gemini", "model": "gemma-4-31b-it"},
        {"provider": "gemini", "model": "google/gemini-2.5-flash"},
    ]
    out = filter_fallback_chain_strip_gemma(chain)
    assert len(out) == 1
    assert "gemini-2.5" in out[0]["model"]


def test_filter_fallback_chain_drops_tier_router_if_any_candidate_is_gemma():
    chain = [
        {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gemini_tier_router": True,
            "gemini_tier_router_tiers": [
                {"models": ["gemini-2.5-flash", "gemma-4-31b-it"]},
            ],
        },
    ]
    assert filter_fallback_chain_strip_gemma(chain) == []


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

