"""Tests for OpenRouter cheap→capable step-up routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.openrouter_step_up import (
    apply_cross_provider_openrouter_first_hop,
    build_ladder_to_ceiling,
    compute_openrouter_step_up_plan,
    content_requests_escalation,
    load_openrouter_step_up_config,
)


def test_build_ladder_to_ceiling_prefix():
    ladder = [
        "openai/gpt-5.4-nano",
        "openai/gpt-5.4-mini",
        "openai/gpt-5.4",
    ]
    assert build_ladder_to_ceiling(ladder, "openai/gpt-5.4-mini") == ladder[:2]


def test_build_ladder_to_ceiling_appends_unknown_ceiling():
    ladder = ["openai/gpt-5.4-nano", "openai/gpt-5.4-mini"]
    out = build_ladder_to_ceiling(ladder, "openai/gpt-5.4")
    assert out[-1] == "openai/gpt-5.4"


def test_content_requests_escalation():
    assert content_requests_escalation("[HERMES_ESCALATE]", "[HERMES_ESCALATE]") is True
    assert content_requests_escalation("  [HERMES_ESCALATE]  ", "[HERMES_ESCALATE]") is True
    assert content_requests_escalation("hello", "[HERMES_ESCALATE]") is False


def test_load_config_defaults():
    cfg = load_openrouter_step_up_config()
    assert "chat_models" in cfg
    assert cfg["chat_models"][0] == "openai/gpt-5-nano"


def test_compute_plan_none_when_not_openrouter():
    class _A:
        model = "openai/gpt-5.4"
        api_mode = "chat_completions"
        _defer_opm_primary_coercion = False
        _skip_per_turn_tier_routing = False
        _model_is_tier_routed = True
        _fallback_activated = False

        def _is_openrouter_url(self):
            return False

    assert compute_openrouter_step_up_plan(_A()) is None


def test_compute_plan_when_openrouter(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    class _A:
        model = "openai/gpt-5.4"
        api_mode = "chat_completions"
        _defer_opm_primary_coercion = False
        _skip_per_turn_tier_routing = False
        _model_is_tier_routed = True
        _fallback_activated = False

        def _is_openrouter_url(self):
            return True

    from agent.routing_canon import invalidate_routing_canon_cache

    invalidate_routing_canon_cache()
    plan = compute_openrouter_step_up_plan(_A())
    assert plan is not None
    assert plan["ladder"][0] == "openai/gpt-5-nano"
    assert plan["start_model"] == "openai/gpt-5-nano"
    assert "[HERMES_ESCALATE]" in (plan.get("system_suffix") or "")


def test_prepare_swaps_start_model(monkeypatch):
    """_prepare_openrouter_step_up_for_turn swaps to ladder[0] when tier ceiling differs."""
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.model = "openai/gpt-5.4"
    agent.api_mode = "chat_completions"
    agent._defer_opm_primary_coercion = False
    agent._skip_per_turn_tier_routing = False
    agent._model_is_tier_routed = True
    agent._fallback_activated = False
    agent._last_opm_meta = {}
    agent.context_compressor = None

    def _or():
        return True

    agent._is_openrouter_url = _or

    called = {"mid": None}

    def _swap(self, mid, **kw):
        called["mid"] = mid
        return True

    monkeypatch.setattr(AIAgent, "_swap_to_openrouter_hub_model", _swap)
    AIAgent._prepare_openrouter_step_up_for_turn(agent)
    assert called["mid"] == "openai/gpt-5-nano"
    assert agent._or_stepup_ladder[0] == "openai/gpt-5-nano"


def test_apply_cross_provider_first_hop_starts_at_cheapest():
    class _A:
        model = "openai/gpt-5.3-codex"
        api_mode = "codex_responses"

    a = _A()
    explicit = ["openai/gpt-5.3-codex", "openai/gpt-5.2-codex"]
    first = apply_cross_provider_openrouter_first_hop(a, explicit)
    assert first == "openai/gpt-5.2-codex"
    assert a._or_stepup_ladder[0] == "openai/gpt-5.2-codex"


def test_quota_escalation_advances_rung(monkeypatch):
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.model = "openai/gpt-5.4-nano"
    agent._or_stepup_escalate_on_quota = True
    agent._or_stepup_ladder = ["openai/gpt-5.4-nano", "openai/gpt-5.4-mini", "openai/gpt-5.4"]
    agent._or_stepup_idx = 0
    agent._or_stepup_escalations = 0
    agent._or_stepup_max_escalations = 12
    agent._last_opm_meta = {}
    agent.context_compressor = None

    swaps = []

    def _swap(self, mid, **kw):
        swaps.append(mid)
        return True

    monkeypatch.setattr(AIAgent, "_swap_to_openrouter_hub_model", _swap)

    class _Err(Exception):
        status_code = 429

    err = _Err("rate limited")
    monkeypatch.setattr(AIAgent, "_quota_style_api_failure", lambda self, e: True)

    ok = AIAgent._try_openrouter_step_up_on_quota(agent, err, pool_may_recover=False)
    assert ok is True
    assert agent._or_stepup_idx == 1
    assert swaps == ["openai/gpt-5.4-mini"]
