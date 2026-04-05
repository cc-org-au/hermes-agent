"""Tests for workspace token governance runtime caps."""

from __future__ import annotations

import pytest
import yaml

from agent.token_governance_runtime import (
    RUNTIME_FILENAME,
    apply_token_governance_runtime,
    load_runtime_config,
)


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    ops = home / "workspace" / "operations"
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
