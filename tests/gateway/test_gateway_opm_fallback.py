"""Gateway cache signature reflects OPM (fallback cleared in AIAgent / resolve_fallback_providers)."""

from unittest.mock import patch


def test_fallback_cache_signature_reflects_opm():
    from gateway.run import GatewayRunner

    runner = GatewayRunner.__new__(GatewayRunner)
    with patch(
        "agent.openai_primary_mode.opm_suppresses_free_model_fallback",
        return_value=True,
    ):
        assert runner._fallback_cache_signature_token() == "opmfb:True"
    with patch(
        "agent.openai_primary_mode.opm_suppresses_free_model_fallback",
        return_value=False,
    ):
        assert runner._fallback_cache_signature_token() == "opmfb:False"


def test_resolve_fallback_providers_empty_under_opm():
    from agent.free_model_routing import resolve_fallback_providers

    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {"router_model": "gemma-4-31b-it", "tiers": []},
        }
    }
    with patch(
        "agent.openai_primary_mode.opm_suppresses_free_model_fallback",
        return_value=True,
    ):
        assert resolve_fallback_providers(cfg) == []


def test_fallback_fingerprint_changes_agent_config_signature():
    from gateway.run import GatewayRunner

    runtime = {
        "api_key": "sk-test",
        "base_url": "https://api.openai.com/v1",
        "provider": "openai",
    }
    sig_a = GatewayRunner._agent_config_signature(
        "gpt-5.4", runtime, ["hermes-telegram"], "", False, "opmfb:False"
    )
    sig_b = GatewayRunner._agent_config_signature(
        "gpt-5.4", runtime, ["hermes-telegram"], "", False, "opmfb:True"
    )
    assert sig_a != sig_b
