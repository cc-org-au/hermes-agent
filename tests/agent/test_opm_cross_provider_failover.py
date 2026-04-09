"""Tests for OPM cross-provider quota failover (routing canon)."""

from __future__ import annotations

import pytest

from agent.opm_cross_provider_failover import (
    load_opm_cross_provider_quota_failover_config,
    norm_model_slug,
    openrouter_explicit_models_for_agent,
)
from agent.routing_canon import invalidate_routing_canon_cache, load_merged_routing_canon


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    invalidate_routing_canon_cache()
    yield home
    invalidate_routing_canon_cache()


def test_merged_canon_includes_cross_provider_block(hermes_home):
    m = load_merged_routing_canon(force_reload=True)
    assert int(m.get("version") or 1) >= 2
    cp = m.get("opm_cross_provider_quota_failover")
    assert isinstance(cp, dict)
    assert "openrouter_chat_models" in cp


def test_load_config_derives_openrouter_from_native_when_empty(hermes_home):
    cfg = load_opm_cross_provider_quota_failover_config()
    assert cfg["enabled"] is True
    assert cfg["openrouter_chat_models"]
    assert all(m.lower().startswith("openai/") for m in cfg["openrouter_chat_models"])


def test_norm_model_slug_strips_openai_prefix():
    assert norm_model_slug("openai/gpt-5.4") == "gpt-5.4"
    assert norm_model_slug("gpt-5.3") == "gpt-5.3"


def test_openrouter_explicit_models_chat_vs_codex():
    class _Chat:
        api_mode = "chat_completions"
        model = "gpt-5.4"

    class _Codex:
        api_mode = "codex_responses"
        model = "gpt-5.3-codex"

    xcfg = load_opm_cross_provider_quota_failover_config()
    chat = openrouter_explicit_models_for_agent(_Chat(), xcfg)
    codex = openrouter_explicit_models_for_agent(_Codex(), xcfg)
    assert "openai/gpt-5.4" in chat or chat[0].startswith("openai/")
    assert codex and ("codex" in codex[0].lower())
