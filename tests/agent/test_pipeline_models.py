"""Tests for agent.pipeline_models.collect_pipeline_models."""

from agent.pipeline_models import collect_pipeline_models


def test_collect_pipeline_models_order_and_dedupe():
    cfg = {
        "model": {"default": "anthropic/claude-sonnet-4"},
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "moonshotai/Kimi-K2-Thinking",
                "tiers": [
                    {
                        "id": "general",
                        "description": "General",
                        "models": ["MiniMaxAI/MiniMax-M2.5", "org/other"],
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
    # Primary first; MiniMax once (tier dedupe); router; tier other; gemini
    assert models[0] == "anthropic/claude-sonnet-4"
    assert models.count("MiniMaxAI/MiniMax-M2.5") == 1
    assert "moonshotai/Kimi-K2-Thinking" in models
    assert "org/other" in models
    assert models[-1] == "gemma-4-31b-it"
    assert rows[-1]["provider_kind"] == "gemini"


def test_collect_pipeline_models_disabled():
    cfg = {
        "model": {"default": "x"},
        "free_model_routing": {"enabled": False},
    }
    rows = collect_pipeline_models(cfg)
    assert len(rows) == 1
    assert rows[0]["model"] == "x"


def test_collect_pipeline_models_kimi_tiers():
    cfg = {
        "model": {"default": "anthropic/claude-sonnet-4"},
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "moonshotai/Kimi-K2-Thinking",
                "tiers": [{"id": "g", "models": ["only-tier-model"]}],
            },
        },
    }
    rows = collect_pipeline_models(cfg)
    models = [r["model"] for r in rows]
    assert "only-tier-model" in models
