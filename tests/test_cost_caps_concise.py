"""Cost caps + concise output config on AIAgent."""

from __future__ import annotations

import pytest

from run_agent import AIAgent


def test_cost_cap_extractive_when_keywords_and_short_user_message(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    def _caps():
        return {
            "enabled": True,
            "extractive_max_output_tokens": 512,
            "extractive_user_message_max_chars": 800,
            "extractive_keywords": ["summarize"],
            "preserve_full_for_tiers": ["E", "F", "G"],
        }

    monkeypatch.setattr("agent.routing_canon.load_cost_caps_config", _caps)
    agent = AIAgent(
        model="openai/gpt-5.4-nano",
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )
    agent._turn_user_text_for_cost_caps = "Please summarize this"
    agent._current_tier_letter = "C"
    assert agent._cost_cap_max_output_for_turn() == 512


def test_cost_cap_skips_for_preserved_tier(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    def _caps():
        return {
            "enabled": True,
            "extractive_max_output_tokens": 512,
            "extractive_user_message_max_chars": 800,
            "extractive_keywords": ["summarize"],
            "preserve_full_for_tiers": ["E", "F", "G"],
        }

    monkeypatch.setattr("agent.routing_canon.load_cost_caps_config", _caps)
    agent = AIAgent(
        model="openai/gpt-5.4-nano",
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )
    agent._turn_user_text_for_cost_caps = "summarize"
    agent._current_tier_letter = "F"
    assert agent._cost_cap_max_output_for_turn() is None


def test_concise_fragment_loaded(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    def _co():
        return {"enabled": True, "ephemeral_fragment": "Be brief."}

    monkeypatch.setattr("agent.routing_canon.load_concise_output_config", _co)
    agent = AIAgent(
        model="openai/gpt-5.4-nano",
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )
    assert agent._concise_output_enabled
    assert agent._concise_output_fragment == "Be brief."
