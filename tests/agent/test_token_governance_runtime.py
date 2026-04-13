"""Tests for workspace token governance runtime caps."""

from __future__ import annotations

import pytest
import yaml

from unittest.mock import patch

from agent.disallowed_model_family import (
    disallowed_family_fixture_slug,
    disallowed_family_openrouter_hub_slug,
)
from agent.token_governance_runtime import (
    RUNTIME_FILENAME,
    apply_per_turn_tier_model,
    apply_token_governance_runtime,
    enforce_opm_runtime_after_per_turn_routing,
    inherit_token_governance_from_parent,
    load_runtime_config,
    resolve_tier_strings_in_config,
)


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    ops = home / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_TOKEN_GOVERNANCE_DISABLE", raising=False)
    monkeypatch.delenv("HERMES_GOVERNANCE_ALLOW_PREMIUM", raising=False)
    return ops


def test_missing_file_returns_none(gov_env, monkeypatch):
    monkeypatch.delenv("HERMES_TOKEN_GOVERNANCE_DISABLE", raising=False)
    assert load_runtime_config() is None


def test_disabled_flag_skips(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(yaml.safe_dump({"enabled": False}), encoding="utf-8")
    assert load_runtime_config() is None


def test_env_disable_skips(gov_env, monkeypatch):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(yaml.safe_dump({"enabled": True, "max_agent_turns": 3}), encoding="utf-8")
    monkeypatch.setenv("HERMES_TOKEN_GOVERNANCE_DISABLE", "1")
    assert load_runtime_config() is None


def test_apply_downgrades_model_and_caps_iterations(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "default_model": "cheap/model",
                # Override builtin Tier B so blocklist replacement matches test expectation.
                "tier_models": {"B": "cheap/model"},
                "blocked_model_substrings": ["opus"],
                "max_agent_turns": 12,
                "delegation_max_iterations": 7,
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "anthropic/claude-opus-4.1"
            self.max_iterations = 90
            self.skip_context_files = False
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://openrouter.ai/api/v1"
            self.iteration_budget = __import__("run_agent", fromlist=["IterationBudget"]).IterationBudget(90)

        def _is_openrouter_url(self):
            return True

    a = _A()
    apply_token_governance_runtime(a)
    assert a.model == "cheap/model"
    assert a.max_iterations == 12
    assert a.iteration_budget.max_total == 12
    assert a._token_governance_delegation_max == 7
    assert a._use_prompt_caching is False


def test_allow_premium_env_skips_downgrade(gov_env, monkeypatch):
    monkeypatch.setenv("HERMES_GOVERNANCE_ALLOW_PREMIUM", "1")
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "default_model": "cheap/model",
                "blocked_model_substrings": ["opus"],
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "anthropic/claude-opus-4.1"
            self.max_iterations = 90
            self.skip_context_files = False
            self.api_mode = "chat_completions"
            self._base_url_lower = ""
            self.iteration_budget = __import__("run_agent", fromlist=["IterationBudget"]).IterationBudget(90)

        def _is_openrouter_url(self):
            return False

    a = _A()
    apply_token_governance_runtime(a)
    assert a.model == "anthropic/claude-opus-4.1"


def test_tier_sentinel_resolves_on_agent(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "tier_models": {"D": "google/gemini-2.5-flash", "B": "google/gemini-2.5-flash-lite"},
                "chief_default_tier": "D",
                "max_agent_turns": 90,
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "tier:D"
            self.max_iterations = 90
            self.skip_context_files = False
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://openrouter.ai/api/v1"
            self.iteration_budget = __import__("run_agent", fromlist=["IterationBudget"]).IterationBudget(90)

        def _is_openrouter_url(self):
            return True

    a = _A()
    apply_token_governance_runtime(a)
    assert a.model == "google/gemini-2.5-flash"


def test_resolve_tier_strings_without_runtime_file_uses_builtin_tiers(gov_env, monkeypatch):
    """When governance YAML is absent, tier:X still resolves via BUILTIN_TIER_MODELS."""
    monkeypatch.delenv("HERMES_TOKEN_GOVERNANCE_DISABLE", raising=False)
    assert load_runtime_config() is None
    out = resolve_tier_strings_in_config({"model": {"default": "tier:D", "provider": "openrouter"}})
    assert out["model"]["default"] == "anthropic/claude-sonnet-4-6"


def test_apply_runtime_resolves_tier_when_governance_disabled(gov_env, monkeypatch):
    """apply_token_governance_runtime must not return before resolving tier:X when YAML missing."""
    monkeypatch.delenv("HERMES_TOKEN_GOVERNANCE_DISABLE", raising=False)
    assert load_runtime_config() is None

    class _A:
        def __init__(self):
            self.model = "tier:D"
            self.max_iterations = 90
            self.skip_context_files = False
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://openrouter.ai/api/v1"

        def _is_openrouter_url(self):
            return True

    a = _A()
    apply_token_governance_runtime(a)
    assert a.model == "anthropic/claude-sonnet-4-6"
    assert getattr(a, "_token_governance_cfg", None) is None


def test_resolve_tier_strings_in_config(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "chief_default_tier": "D",
                "tier_models": {"D": "m-d", "B": "m-b"},
            }
        ),
        encoding="utf-8",
    )
    out = resolve_tier_strings_in_config({"model": {"default": "tier:B", "provider": "openrouter"}})
    assert out["model"]["default"] == "m-b"


def test_resolve_tier_strings_preserves_tier_dynamic(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "chief_default_tier": "D",
                "tier_models": {"D": "m-d", "B": "m-b"},
            }
        ),
        encoding="utf-8",
    )
    out = resolve_tier_strings_in_config(
        {"auxiliary": {"compression": {"model": "tier:dynamic", "provider": "openrouter"}}}
    )
    assert out["auxiliary"]["compression"]["model"] == "tier:dynamic"


def test_per_turn_selects_tier_b(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "tier_models": {"B": "cheap-b", "D": "main-d"},
                "default_routing_tier": "D",
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "main-d"
            self.api_mode = "chat_completions"
            self._base_url_lower = "openrouter"

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    apply_per_turn_tier_model(a, "summarize the following paragraph in three bullets")
    assert a.model == "cheap-b"


def test_per_turn_tier_dynamic_resolves(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": False,
                "tier_models": {"B": "cheap-b", "D": "main-d"},
                "default_routing_tier": "D",
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "tier:dynamic"
            self.api_mode = "chat_completions"
            self._base_url_lower = "openrouter"

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    apply_per_turn_tier_model(a, "summarize the following paragraph in three bullets")
    assert a.model == "cheap-b"


def test_per_turn_skipped_when_fallback_active_non_openrouter(gov_env):
    """Pinned fallback on direct Gemini (etc.): do not override model each turn."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "tier_models": {"B": "cheap-b", "D": "main-d"},
                "default_routing_tier": "D",
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "gemini-2.5-flash"
            self.api_mode = "chat_completions"
            self._base_url_lower = "googleapis"
            self._fallback_activated = True

        def _is_openrouter_url(self):
            return False

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    apply_per_turn_tier_model(a, "summarize the following paragraph in three bullets")
    assert a.model == "gemini-2.5-flash"


def test_per_turn_applies_when_fallback_active_openrouter(gov_env):
    """OpenRouter fallback: still pick tier_models per turn (mini vs full, etc.)."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "tier_models": {"B": "openai/gpt-5.4-nano", "D": "openai/gpt-5.4"},
                "default_routing_tier": "D",
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "openai/gpt-5.4"
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://openrouter.ai/api/v1"
            self._fallback_activated = True

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    apply_per_turn_tier_model(a, "summarize the following paragraph in three bullets")
    assert a.model == "openai/gpt-5.4-nano"


def test_per_turn_skipped_when_pipeline_model_once(gov_env):
    """Manual /models selection: do not override model for this turn."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "tier_models": {"B": "cheap-b", "D": "main-d"},
                "default_routing_tier": "D",
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "user-picked-model"
            self.api_mode = "chat_completions"
            self._base_url_lower = "openrouter"
            self._skip_per_turn_tier_routing = True

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    apply_per_turn_tier_model(a, "summarize the following paragraph in three bullets")
    assert a.model == "user-picked-model"


def test_openai_primary_mode_enforced_after_consultant_routing(gov_env, monkeypatch):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "default_routing_tier": "D",
                "openai_primary_mode": {
                    "enabled": True,
                    "default_model": "gpt-5.4",
                    "codex_model": "gpt-5.3-codex",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "agent.consultant_routing.consultant_routing_enabled",
        lambda _cfg: True,
    )
    monkeypatch.setattr(
        "agent.consultant_routing.resolve_consultant_tier",
        lambda *args, **kwargs: ("A", {"router": {"coding_task": False}}),
    )
    monkeypatch.setattr(
        "agent.consultant_routing.is_pushback_message",
        lambda _msg: False,
    )
    monkeypatch.setattr(
        "agent.consultant_routing.format_status_line",
        lambda *_args, **_kwargs: "",
    )

    class _A:
        def __init__(self):
            self.model = "tier:dynamic"
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://generativelanguage.googleapis.com"

        def _is_openrouter_url(self):
            return False

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    a._model_is_tier_routed = True
    apply_per_turn_tier_model(a, "summarize this quickly")
    assert a.model == "gpt-5.4"


def test_apply_token_governance_skips_blocklist_when_defer_pipeline_opm(gov_env):
    """CLI /models manual route must not downgrade openai/gpt-5.4 via blocked_model_substrings."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "blocked_model_substrings": ["gpt-5"],
                "default_model": "google/gemini-2.5-flash",
                "tier_models": {"D": "google/gemini-2.5-flash"},
            }
        ),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "openai/gpt-5.4"
            self.api_mode = "chat_completions"
            self.max_iterations = 90
            self._base_url_lower = "openrouter.ai"
            self._delegate_depth = 0

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._defer_opm_primary_coercion = True
    apply_token_governance_runtime(a)
    assert a.model == "openai/gpt-5.4"


def test_apply_token_governance_opm_does_not_force_tier_placeholder_when_defer(gov_env):
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump({"enabled": True, "tier_models": {"D": "google/gemini-2.5-flash"}}),
        encoding="utf-8",
    )

    class _A:
        def __init__(self):
            self.model = "openai/gpt-5.4"
            self.api_mode = "chat_completions"
            self.max_iterations = 90
            self._base_url_lower = "openrouter"
            self._delegate_depth = 0

        def _is_openrouter_url(self):
            return True

    a = _A()
    a._defer_opm_primary_coercion = True
    with patch("agent.token_governance_runtime.opm_enabled", return_value=True):
        apply_token_governance_runtime(a)
    assert a._model_is_tier_routed is False


def test_inherit_respects_child_defer_opm_for_tier_routed_flag():
    parent = type("_P", (), {})()
    parent._token_governance_cfg = {
        "enabled": True,
        "openai_primary_mode": {"enabled": True},
    }
    child = type("_C", (), {})()
    child.model = "openai/gpt-5.4"
    child._token_governance_cfg = None
    child._defer_opm_primary_coercion = True
    with patch(
        "agent.token_governance_runtime.resolve_openai_primary_mode",
        return_value=({}, {"enabled": True}),
    ):
        inherit_token_governance_from_parent(child, parent)
    assert child._model_is_tier_routed is False


def test_inherit_token_governance_from_parent_opm_forces_tier_routed():
    """Child with no cached cfg inherits parent's runtime dict so OPM can uplift tiers."""
    parent = type("_P", (), {})()
    parent._token_governance_cfg = {
        "enabled": True,
        "dynamic_tier_routing": True,
        "tier_models": {"E": "openai/gpt-5.4"},
        "openai_primary_mode": {"enabled": True},
    }
    child = type("_C", (), {})()
    child.model = disallowed_family_openrouter_hub_slug()
    child._token_governance_cfg = None
    child._model_is_tier_routed = False

    with patch(
        "agent.token_governance_runtime.resolve_openai_primary_mode",
        return_value=({}, {"enabled": True, "source": "parent_cached"}),
    ):
        inherit_token_governance_from_parent(child, parent)

    assert child._token_governance_cfg is parent._token_governance_cfg
    assert child._model_is_tier_routed is True
    assert child._last_opm_meta["enabled"] is True


def test_inherit_token_governance_noop_when_child_already_has_cfg():
    parent = type("_P", (), {})()
    parent._token_governance_cfg = {"enabled": True}
    child = type("_C", (), {})()
    child._token_governance_cfg = {"enabled": True, "tier_models": {}}
    inherit_token_governance_from_parent(child, parent)
    assert child._token_governance_cfg == {"enabled": True, "tier_models": {}}


def test_inherit_falls_back_to_disk_when_parent_has_no_cached_cfg(gov_env, monkeypatch):
    """Parent may lack _token_governance_cfg; still load from HERMES_HOME file for the child."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "tier_models": {"E": "gpt-5.4", "F": "gpt-5.3-codex"},
                "openai_primary_mode": {"enabled": True, "default_model": "gpt-5.4"},
            }
        ),
        encoding="utf-8",
    )
    parent = type("_P", (), {})()
    child = type("_C", (), {})()
    child.model = "tier:dynamic"
    child._token_governance_cfg = None
    with patch(
        "agent.token_governance_runtime.resolve_openai_primary_mode",
        return_value=({}, {"enabled": True}),
    ):
        inherit_token_governance_from_parent(child, parent)
    assert child._token_governance_cfg.get("enabled") is True
    assert child._token_governance_cfg.get("tier_models", {}).get("E") == "gpt-5.4"


def test_opm_clamp_replaces_google_gemini_tier_slug():
    from agent import token_governance_runtime as tgr

    agent = object()
    with (
        patch(
            "agent.token_governance_runtime.opm_enabled",
            return_value=True,
        ),
        patch(
            "agent.token_governance_runtime.resolve_openai_primary_mode",
            return_value=(
                {"default_model": "gpt-5.4", "codex_model": "gpt-5.3-codex"},
                {"enabled": True},
            ),
        ),
    ):
        out = tgr._opm_clamp_tier_resolved_model(
            agent, "google/gemini-2.5-flash", "summarize", {"enabled": True}
        )
    assert out == "gpt-5.4"


def test_opm_clamp_trivial_message_prefers_cheapest_native_ladder_rung():
    """Ping-class prompts should map to nano/mini ladder rung, not the OPM default flagship."""
    from agent import token_governance_runtime as tgr

    agent = object()
    with (
        patch(
            "agent.token_governance_runtime.opm_enabled",
            return_value=True,
        ),
        patch(
            "agent.token_governance_runtime.resolve_openai_primary_mode",
            return_value=(
                {"default_model": "gpt-5.4", "codex_model": "gpt-5.3-codex"},
                {"enabled": True},
            ),
        ),
    ):
        out = tgr._opm_clamp_tier_resolved_model(
            agent, "google/gemini-2.5-flash", "ping", {"enabled": True}
        )
    assert out == "gpt-5.4-nano"


def test_trivial_ping_skips_opm_uplift_and_clamps_gemini_to_cheapest(gov_env, monkeypatch):
    """Consultant tier A + trivial message must not be uplifted to E; clamp uses ladder nano."""
    p = gov_env / RUNTIME_FILENAME
    p.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "dynamic_tier_routing": True,
                "default_routing_tier": "D",
                "tier_models": {"A": "google/gemini-2.5-flash"},
                "openai_primary_mode": {
                    "enabled": True,
                    "default_model": "gpt-5.4",
                    "codex_model": "gpt-5.3-codex",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "agent.consultant_routing.consultant_routing_enabled",
        lambda _cfg: True,
    )
    monkeypatch.setattr(
        "agent.consultant_routing.resolve_consultant_tier",
        lambda *args, **kwargs: ("A", {"router": {"coding_task": False}}),
    )
    monkeypatch.setattr(
        "agent.consultant_routing.is_pushback_message",
        lambda _msg: False,
    )
    monkeypatch.setattr(
        "agent.consultant_routing.format_status_line",
        lambda *_args, **_kwargs: "",
    )

    class _A:
        def __init__(self):
            self.model = "tier:dynamic"
            self.api_mode = "chat_completions"
            self._base_url_lower = "https://api.openai.com/v1"

        def _is_openrouter_url(self):
            return False

    a = _A()
    a._token_governance_cfg = load_runtime_config()
    a._model_is_tier_routed = True
    apply_per_turn_tier_model(a, "ping")
    assert a.model == "gpt-5.4-nano"


def test_enforce_opm_runtime_after_per_turn_routing_fixes_skipped_tier_path():
    """Even when apply_per_turn exited early, run_conversation enforcement can fix disallowed ids."""

    class _StubAgent:
        def __init__(self):
            self.model = disallowed_family_fixture_slug()
            self.provider = "gemini"
            self.base_url = "https://generativelanguage.googleapis.com/v1beta"
            self._reconcile_called = False

        def _reconcile_runtime_after_tier_model_change(self):
            self._reconcile_called = True

    agent = _StubAgent()
    with (
        patch(
            "agent.token_governance_runtime.opm_enabled",
            return_value=True,
        ),
        patch(
            "agent.token_governance_runtime.resolve_openai_primary_mode",
            return_value=(
                {"default_model": "gpt-5.4", "codex_model": "gpt-5.3-codex"},
                {"enabled": True, "source": "test"},
            ),
        ),
    ):
        enforce_opm_runtime_after_per_turn_routing(agent, "summarize the doc")
    assert agent.model == "gpt-5.4"
    assert agent._reconcile_called is True


def test_enforce_opm_runtime_respects_defer_opm_primary_coercion():
    """CLI /models route sets _defer_opm_primary_coercion; OPM must not rewrite the model."""

    class _StubAgent:
        def __init__(self):
            self.model = "google/gemini-2.5-flash"
            self.provider = "openrouter"
            self.base_url = "https://openrouter.ai/api/v1"
            self._defer_opm_primary_coercion = True
            self._reconcile_called = False

        def _reconcile_runtime_after_tier_model_change(self):
            self._reconcile_called = True

    agent = _StubAgent()
    with patch("agent.token_governance_runtime.opm_enabled", return_value=True):
        enforce_opm_runtime_after_per_turn_routing(agent, "summarize the doc")
    assert agent.model == "google/gemini-2.5-flash"
    assert agent._reconcile_called is False


def test_opm_reconcile_skips_when_defer_opm_primary_coercion():
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.model = "openrouter/auto"
    agent._defer_opm_primary_coercion = True
    AIAgent._opm_reconcile_primary_if_disallowed(agent)
    assert agent.model == "openrouter/auto"


def test_reconcile_runtime_leaves_openrouter_when_defer_pipeline_opm():
    """openai/gpt-5.4 is a native-consultant core id once stripped; /models OpenRouter shortcut must not jump to api.openai.com."""
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.model = "openai/gpt-5.4"
    agent.provider = "openrouter"
    agent.base_url = "https://openrouter.ai/api/v1"
    agent.api_key = "sk-or-test"
    agent.api_mode = "chat_completions"
    agent._client_kwargs = {"api_key": agent.api_key, "base_url": agent.base_url}
    agent._defer_opm_primary_coercion = True
    agent._inference_runtime_snapshot = {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "sk-or-test",
        "api_mode": "chat_completions",
    }
    AIAgent._reconcile_runtime_after_tier_model_change(agent)
    assert agent.base_url == "https://openrouter.ai/api/v1"
    assert agent.model == "openai/gpt-5.4"


def test_tier_targets_native_consultant_false_when_defer_pipeline_opm():
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent._defer_opm_primary_coercion = True
    assert AIAgent._tier_targets_openai_native_consultant(agent, "openai/gpt-5.4") is False
