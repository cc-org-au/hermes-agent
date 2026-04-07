"""Tests for agent.pipeline_models.collect_pipeline_models."""

from agent.pipeline_models import (
    MENU_ACTION_CHOOSE_ROUTER,
    MENU_ACTION_OPENROUTER_BROWSE,
    PROVIDER_KIND_OPENAI_NATIVE,
    PROVIDER_KIND_OPENAI_NATIVE_ROUTER,
    collect_models_menu_entries,
    collect_pipeline_models,
    collect_router_picker_model_rows,
)


def test_collect_pipeline_models_order_and_dedupe():
    cfg = {
        "model": {"default": "anthropic/claude-sonnet-4"},
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": False,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "router_provider": "gemini",
                "tiers": [
                    {
                        "id": "general",
                        "description": "General",
                        "models": ["Qwen/QwQ-32B", "org/other"],
                    },
                ],
            },
            "optional_gemini": {
                "enabled": True,
                "model": "gemma-4-31b-it",
            },
        },
    }
    rows = collect_pipeline_models(cfg)
    models = [r["model"] for r in rows]
    # Primary first; router (gemma-4 = gemini); Qwen + tier other; optional_gemini dedupes gemma-4
    assert models[0] == "anthropic/claude-sonnet-4"
    assert models.count("Qwen/QwQ-32B") == 1
    assert "gemma-4-31b-it" in models
    assert "org/other" in models
    g4 = [r for r in rows if r["model"] == "gemma-4-31b-it"]
    assert g4 and all(r["provider_kind"] == "gemini" for r in g4)


def test_collect_pipeline_models_disabled():
    cfg = {
        "model": {"default": "x"},
        "free_model_routing": {"enabled": False},
    }
    rows = collect_pipeline_models(cfg)
    assert len(rows) == 1
    assert rows[0]["model"] == "x"


def test_collect_pipeline_models_routing_tiers():
    cfg = {
        "model": {"default": "anthropic/claude-sonnet-4"},
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": False,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "router_provider": "gemini",
                "tiers": [{"id": "g", "models": ["only-tier-model"]}],
            },
        },
    }
    rows = collect_pipeline_models(cfg)
    models = [r["model"] for r in rows]
    assert "only-tier-model" in models


def test_collect_pipeline_models_skips_blocklisted_ids():
    cfg = {
        "model": {"default": "anthropic/claude-sonnet-4"},
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": False,
            "kimi_router": {
                "router_model": "deepseek/deepseek-chat",
                "router_provider": "gemini",
                "tiers": [
                    {
                        "id": "t",
                        "models": ["Qwen/Qwen2.5-7B", "moonshotai/kimi-k2.5"],
                    },
                ],
            },
        },
    }
    rows = collect_pipeline_models(cfg)
    models = [r["model"] for r in rows]
    assert "moonshotai/kimi-k2.5" not in models
    assert "deepseek/deepseek-chat" not in models
    assert "Qwen/Qwen2.5-7B" in models


def test_collect_models_menu_entries_includes_actions_and_shortcuts():
    cfg = {"model": {"default": "openai/gpt-5.4"}, "free_model_routing": {"enabled": False}}
    entries = collect_models_menu_entries(cfg)
    actions = [e for e in entries if e.get("kind") == "action"]
    assert any(a.get("action") == MENU_ACTION_OPENROUTER_BROWSE for a in actions)
    assert any(a.get("action") == MENU_ACTION_CHOOSE_ROUTER for a in actions)
    mids = [e["model"] for e in entries if e.get("kind") == "model"]
    assert "openrouter/auto" in mids
    assert "openai/gpt-5.4" in mids
    assert "gpt-5.4" in mids
    native = [e for e in entries if e.get("kind") == "model" and e["model"] == "gpt-5.4"]
    assert any(r.get("provider_kind") == PROVIDER_KIND_OPENAI_NATIVE for r in native)


def test_collect_router_picker_leads_with_native_openai_rows():
    rows = collect_router_picker_model_rows()
    assert rows[0]["model"] == "gpt-5.4"
    assert rows[0]["provider_kind"] == PROVIDER_KIND_OPENAI_NATIVE_ROUTER
    assert rows[1]["model"] == "gpt-5.3-codex"
