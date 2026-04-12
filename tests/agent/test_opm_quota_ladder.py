"""Tests for OPM native quota downgrade ladder (routing_canon)."""

from __future__ import annotations

import pytest
import yaml

from agent.opm_quota_ladder import (
    load_opm_native_quota_downgrade_config,
    next_quota_downgrade_model,
    session_budget_next_cheaper_model,
    should_attempt_opm_native_downgrade,
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


def test_merged_canon_includes_opm_quota_ladder(hermes_home):
    m = load_merged_routing_canon(force_reload=True)
    oq = m.get("opm_native_quota_downgrade")
    assert isinstance(oq, dict)
    assert "chat_models" in oq
    assert "codex_models" in oq


def test_normalize_ladder_maps_legacy_gpt53_to_official_mini():
    cfg = load_opm_native_quota_downgrade_config()
    chat = cfg.get("chat_models") or []
    assert "gpt-5.3" not in chat
    assert "gpt-5.4-mini" in chat


def test_session_budget_next_cheaper_model_preserves_openrouter_prefix():
    """Session cost path keeps ``openai/`` when stepping the ladder on OpenRouter."""
    assert (
        session_budget_next_cheaper_model(
            current_model="openai/gpt-5.4",
            base_url="https://openrouter.ai/api/v1",
            api_mode="chat_completions",
        )
        == "openai/gpt-5.2"
    )


def test_session_budget_next_cheaper_model_native_matches_bare_ladder():
    assert (
        session_budget_next_cheaper_model(
            current_model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            api_mode="chat_completions",
        )
        == "gpt-5.2"
    )


def test_next_quota_downgrade_model_chat():
    cfg = load_opm_native_quota_downgrade_config()
    assert (
        next_quota_downgrade_model(
            current_model="gpt-5.4",
            api_mode="chat_completions",
            cfg=cfg,
        )
        == "gpt-5.2"
    )
    assert (
        next_quota_downgrade_model(
            current_model="gpt-5.4-mini",
            api_mode="chat_completions",
            cfg=cfg,
        )
        == "gpt-5-mini"
    )
    assert next_quota_downgrade_model(
        current_model="openai/gpt-5.4-nano",
        api_mode="chat_completions",
        cfg=cfg,
    ) == "gpt-5-nano"
    # Legacy mistaken id in session — alias maps to gpt-5.4-mini; next step is cheaper.
    assert next_quota_downgrade_model(
        current_model="openai/gpt-5.3",
        api_mode="chat_completions",
        cfg=cfg,
    ) == "gpt-5-mini"
    assert (
        next_quota_downgrade_model(
            current_model="gpt-4.1-nano",
            api_mode="chat_completions",
            cfg=cfg,
        )
        is None
    )


def test_next_quota_downgrade_gpt54_on_codex_api_stack():
    """Native OpenAI uses codex_responses while the slug is chat-tier (gpt-5.4)."""
    cfg = load_opm_native_quota_downgrade_config()
    assert (
        next_quota_downgrade_model(
            current_model="gpt-5.4",
            api_mode="codex_responses",
            cfg=cfg,
        )
        == "gpt-5.2"
    )


def test_next_quota_downgrade_model_codex():
    cfg = load_opm_native_quota_downgrade_config()
    assert next_quota_downgrade_model(
        current_model="gpt-5.3-codex",
        api_mode="codex_responses",
        cfg=cfg,
    ) == "gpt-5.2-codex"
    assert (
        next_quota_downgrade_model(
            current_model="gpt-5.2-codex",
            api_mode="codex_responses",
            cfg=cfg,
        )
        is None
    )


def test_overlay_disables_ladder(hermes_home):
    (hermes_home / "routing_canon.yaml").write_text(
        yaml.safe_dump({"opm_native_quota_downgrade": {"enabled": False}}),
        encoding="utf-8",
    )
    invalidate_routing_canon_cache()
    cfg = load_opm_native_quota_downgrade_config()
    assert cfg["enabled"] is False


def test_should_attempt_requires_opm_and_native_openai(hermes_home):
    class _Ag:
        _fallback_activated = False

        def _is_direct_openai_url(self):
            return True

    ok, _cfg = should_attempt_opm_native_downgrade(
        _Ag(),
        quota_style=True,
        pool_may_recover=False,
    )
    assert ok is False  # opm_enabled false for stub agent
