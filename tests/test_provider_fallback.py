"""Tests for ordered provider fallback chain (salvage of PR #1761).

Extends the single-fallback tests in test_fallback_model.py to cover
the new list-based ``fallback_providers`` config format and chain
advancement through multiple providers.
"""

from unittest.mock import MagicMock, patch

from run_agent import AIAgent


def _sample_free_routing_config():
    return {
        "fallback_providers": None,
        "free_model_routing": {
            "enabled": True,
            "openrouter_last_resort": {"enabled": False},
            "kimi_router": {
                "router_model": "test/router",
                "tiers": [{"id": "t0", "models": ["test/a", "test/b"]}],
            },
        },
    }


def _make_agent(fallback_model=None):
    """Create a minimal AIAgent with optional fallback config."""
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            fallback_model=fallback_model,
        )
        agent.client = MagicMock()
        return agent


def _mock_client(base_url="https://openrouter.ai/api/v1", api_key="fb-key"):
    mock = MagicMock()
    mock.base_url = base_url
    mock.api_key = api_key
    return mock


# ── Chain initialisation ──────────────────────────────────────────────────


class TestFallbackChainInit:
    @patch("hermes_cli.config.load_config", return_value=_sample_free_routing_config())
    def test_no_fallback(self, _mock_lc):
        agent = _make_agent(fallback_model=None)
        # Omitted fallback_model: synthesized from free_model_routing (openrouter/free first).
        assert len(agent._fallback_chain) == 2
        assert agent._fallback_chain[0]["provider"] == "openrouter"
        assert agent._fallback_chain[0]["model"] == "openrouter/free"
        assert agent._fallback_chain[1]["provider"] == "gemini"
        assert agent._fallback_chain[1].get("gemini_tier_router") is True
        assert agent._fallback_index == 0
        assert agent._fallback_model == agent._fallback_chain[0]

    def test_openrouter_free_primary_disables_fallback_chain(self):
        agent = _make_agent(
            fallback_model=[
                {"provider": "gemini", "model": "gemini-2.5-flash"},
                {"provider": "openrouter", "model": "openai/gpt-5.4"},
            ]
        )
        agent.model = "openrouter/free"
        agent.provider = "openrouter"
        agent.base_url = "https://openrouter.ai/api/v1"

        agent._suppress_fallback_chain_for_strict_openrouter_free_primary()

        assert agent._fallback_chain == []

    def test_single_dict_backwards_compat(self):
        fb = {"provider": "openai", "model": "gpt-4o"}
        agent = _make_agent(fallback_model=fb)
        assert agent._fallback_chain == [fb]
        assert agent._fallback_model == fb

    def test_list_of_providers(self):
        fbs = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "zai", "model": "glm-4.7"},
        ]
        agent = _make_agent(fallback_model=fbs)
        assert len(agent._fallback_chain) == 2
        assert agent._fallback_model == fbs[0]

    def test_invalid_entries_filtered(self):
        fbs = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "", "model": "glm-4.7"},
            {"provider": "zai"},
            "not-a-dict",
        ]
        agent = _make_agent(fallback_model=fbs)
        assert len(agent._fallback_chain) == 1
        assert agent._fallback_chain[0]["provider"] == "openai"

    def test_empty_list(self):
        agent = _make_agent(fallback_model=[])
        assert agent._fallback_chain == []
        assert agent._fallback_model is None

    def test_explicit_disallowed_fallback_replaced_when_opm_blocks(self):
        """Gateway passes config fallback_providers verbatim; OPM must still strip disallowed ids."""
        from agent.disallowed_model_family import disallowed_family_fixture_slug

        with (
            patch("agent.token_governance_runtime.apply_token_governance_runtime", lambda a: None),
            patch("agent.openai_primary_mode.opm_enabled", return_value=True),
            patch("agent.openai_primary_mode.opm_suppresses_free_model_fallback", return_value=False),
            patch(
                "agent.openai_primary_mode.opm_auxiliary_model",
                return_value="gemini-2.5-flash",
            ),
        ):
            agent = _make_agent(
                fallback_model=[{"provider": "gemini", "model": disallowed_family_fixture_slug()}],
            )
            agent.client = MagicMock()
        assert len(agent._fallback_chain) == 1
        assert agent._fallback_chain[0]["provider"] == "gemini"
        assert agent._fallback_chain[0]["model"] == "gemini-2.5-flash"

    def test_invalid_dict_no_provider(self):
        agent = _make_agent(fallback_model={"model": "gpt-4o"})
        assert agent._fallback_chain == []


# ── Chain advancement ─────────────────────────────────────────────────────


class TestFallbackChainAdvancement:
    def test_exhausted_returns_false(self):
        agent = _make_agent(fallback_model=[])
        assert agent._try_activate_fallback() is False

    def test_advances_index(self):
        fbs = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "zai", "model": "glm-4.7"},
        ]
        agent = _make_agent(fallback_model=fbs)
        with patch("agent.auxiliary_client.resolve_provider_client",
                    return_value=(_mock_client(), "gpt-4o")):
            assert agent._try_activate_fallback() is True
            assert agent._fallback_index == 1
            assert agent.model == "gpt-4o"
            assert agent._fallback_activated is True

    def test_second_fallback_works(self):
        fbs = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "zai", "model": "glm-4.7"},
        ]
        agent = _make_agent(fallback_model=fbs)
        with patch("agent.auxiliary_client.resolve_provider_client",
                    return_value=(_mock_client(), "resolved")):
            assert agent._try_activate_fallback() is True
            assert agent.model == "gpt-4o"
            assert agent._try_activate_fallback() is True
            assert agent.model == "glm-4.7"
            assert agent._fallback_index == 2

    def test_all_exhausted_returns_false(self):
        fbs = [{"provider": "openai", "model": "gpt-4o"}]
        agent = _make_agent(fallback_model=fbs)
        with patch("agent.auxiliary_client.resolve_provider_client",
                    return_value=(_mock_client(), "gpt-4o")):
            assert agent._try_activate_fallback() is True
            assert agent._try_activate_fallback() is False

    def test_skips_unconfigured_provider_to_next(self):
        """If resolve_provider_client returns None, skip to next in chain."""
        fbs = [
            {"provider": "broken", "model": "nope"},
            {"provider": "openai", "model": "gpt-4o"},
        ]
        agent = _make_agent(fallback_model=fbs)
        with patch("agent.auxiliary_client.resolve_provider_client") as mock_rpc:
            mock_rpc.side_effect = [
                (None, None),                    # broken provider
                (_mock_client(), "gpt-4o"),       # fallback succeeds
            ]
            assert agent._try_activate_fallback() is True
            assert agent.model == "gpt-4o"
            assert agent._fallback_index == 2

    def test_skips_provider_that_raises_to_next(self):
        """If resolve_provider_client raises, skip to next in chain."""
        fbs = [
            {"provider": "broken", "model": "nope"},
            {"provider": "openai", "model": "gpt-4o"},
        ]
        agent = _make_agent(fallback_model=fbs)
        with patch("agent.auxiliary_client.resolve_provider_client") as mock_rpc:
            mock_rpc.side_effect = [
                RuntimeError("auth failed"),
                (_mock_client(), "gpt-4o"),
            ]
            assert agent._try_activate_fallback() is True
            assert agent.model == "gpt-4o"


class TestQuotaStyleApiFailure:
    def test_402_triggers(self):
        class _E(Exception):
            status_code = 402

        assert AIAgent._quota_style_api_failure(_E("pay")) is True

    def test_insufficient_credits_message(self):
        assert AIAgent._quota_style_api_failure(
            RuntimeError("Error: insufficient credits on OpenRouter")
        ) is True

    def test_403_openrouter_key_limit_with_body(self):
        class _E(Exception):
            status_code = 403
            body = {
                "message": "Key limit exceeded (total limit). Manage it using https://openrouter.ai/settings/keys",
                "code": 403,
            }

        assert AIAgent._quota_style_api_failure(_E()) is True

    def test_key_limit_message_without_status_code(self):
        """SDK may omit status_code; body/str still carry OpenRouter key-cap text."""
        exc = RuntimeError(
            "Error code: 403 - {'error': {'message': 'Key limit exceeded (total limit). "
            "Manage it using https://openrouter.ai/settings/keys', 'code': 403}}"
        )
        assert AIAgent._quota_style_api_failure(exc) is True


class TestOnlyRateLimitFallback:
    def test_only_rate_limit_skips_without_rate_limit_flag(self):
        fb = {
            "provider": "openai",
            "model": "gpt-4o",
            "only_rate_limit": True,
        }
        agent = _make_agent(fallback_model=fb)
        assert agent._try_activate_fallback(triggered_by_rate_limit=False) is False
        assert agent._fallback_activated is False
        assert agent._fallback_index == 0

    def test_only_rate_limit_activates_when_rate_limited(self):
        fb = {
            "provider": "openai",
            "model": "gpt-4o",
            "only_rate_limit": True,
        }
        agent = _make_agent(fallback_model=fb)
        with patch("agent.auxiliary_client.resolve_provider_client",
                    return_value=(_mock_client(), "gpt-4o")):
            assert agent._try_activate_fallback(triggered_by_rate_limit=True) is True
        assert agent._fallback_activated is True
