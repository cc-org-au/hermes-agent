"""Lazy tool surface (API subset, full prompt names)."""

from __future__ import annotations

import json

import pytest

from run_agent import AIAgent


@pytest.fixture
def lazy_config_on(monkeypatch):
    def _lazy():
        return {
            "enabled": True,
            "core_toolsets": ["memory"],
            "core_tools": [],
            "expand_via": "meta_tool",
        }

    monkeypatch.setattr("agent.routing_canon.load_lazy_tool_loading_config", _lazy)


def test_lazy_reduces_api_tools_but_keeps_prompt_names(tmp_path, monkeypatch, lazy_config_on):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    (tmp_path / ".hermes").mkdir(parents=True)

    agent = AIAgent(
        model="openai/gpt-5.4-nano",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=["memory", "todo"],
    )
    assert agent._lazy_tool_loading_enabled
    names_api = {t["function"]["name"] for t in agent.tools}
    assert "memory" in names_api
    assert "expand_tool_surface" in names_api
    assert "todo" in agent.valid_tool_names
    assert "todo" not in names_api


def test_expand_tool_surface_adds_tools(tmp_path, monkeypatch, lazy_config_on):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    (tmp_path / ".hermes").mkdir(parents=True)

    agent = AIAgent(
        model="openai/gpt-5.4-nano",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=["memory", "todo"],
    )
    raw = agent._expand_lazy_tool_surface(["todo"])
    data = json.loads(raw)
    assert data.get("success") is True
    assert "todo" in data.get("added", [])
    assert "todo" in {t["function"]["name"] for t in agent.tools}
