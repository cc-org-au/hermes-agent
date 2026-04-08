"""Tests for config-driven free_model_routing (no hardcoded hub ids in code)."""

from agent.free_model_routing import (
    build_free_fallback_chain,
    normalize_kimi_tiers,
    resolve_fallback_providers,
)


def test_normalize_kimi_tiers_list_of_dicts():
    t = normalize_kimi_tiers(
        [
            {"id": "a", "description": "d0", "models": ["m1", "m2"]},
            {"models": ["m3"]},
        ]
    )
    assert len(t) == 2
    assert t[0]["models"] == ["m1", "m2"]
    assert t[1]["id"] == "tier-1"
    assert t[1]["models"] == ["m3"]


def test_top_level_tiers_preferred_over_legacy_kimi_router():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": False,
            "tiers": [{"id": "top", "models": ["org/top"]}],
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "legacy", "models": ["org/legacy"]}],
            },
        }
    }
    ch = build_free_fallback_chain(cfg)
    assert ch
    flat = [m for t in ch[0]["gemini_tier_router_tiers"] for m in t["models"]]
    assert "org/top" in flat
    assert "org/legacy" not in flat


def test_fallback_tier_when_all_hub_models_filtered(monkeypatch):
    monkeypatch.setattr(
        "agent.free_model_routing.filter_hub_model_ids_by_local_state",
        lambda ids, enabled=True: [],
    )
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": True,
            "fallback_free_routed_model": "gemma-4-31b-it",
            "gemini_native_tier_models": ["gemma-4-31b-it"],
            "kimi_router": {
                "router_provider": "gemini",
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "local", "models": ["org/local-32b"]}],
            },
        }
    }
    ch = build_free_fallback_chain(cfg)
    assert ch
    assert ch[0].get("gemini_tier_router") is True
    flat = [m for t in ch[0]["gemini_tier_router_tiers"] for m in t["models"]]
    assert "gemma-4-31b-it" in flat


def test_build_chain_kimi_then_optional_gemini():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "t", "models": ["org/a", "org/b"]}],
            },
            "optional_gemini": {
                "enabled": True,
                "model": "gemma-test",
                "only_rate_limit": True,
                "restore_health_check": True,
            },
            "openrouter_last_resort": {"enabled": False},
        }
    }
    ch = build_free_fallback_chain(cfg)
    assert len(ch) == 2
    assert ch[0]["gemini_tier_router"] is True
    assert ch[0]["provider"] == "gemini"
    assert ch[0]["model"] == "gemma-4-31b-it"
    assert len(ch[0]["gemini_tier_router_tiers"]) == 1
    assert "gemma-4-31b-it" in (ch[0].get("gemini_native_tier_models") or [])
    assert ch[1]["provider"] == "gemini"


def test_filtered_tiers_preserve_gemini_native_models(monkeypatch):
    monkeypatch.setattr(
        "agent.free_model_routing.filter_hub_model_ids_by_local_state",
        lambda ids, enabled=True: [x for x in ids if "org/local" not in x],
    )
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "filter_free_tier_models_by_local_hub": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "local", "models": ["gemma-4-31b-it", "org/local-32b"]}],
            },
        }
    }
    ch = build_free_fallback_chain(cfg)
    assert ch
    flat = [m for t in ch[0]["gemini_tier_router_tiers"] for m in t["models"]]
    assert "gemma-4-31b-it" in flat
    assert "org/local-32b" not in flat


def test_build_chain_router_provider_gemini():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_provider": "gemini",
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "t", "models": ["org/a", "org/b"]}],
            },
            "openrouter_last_resort": {"enabled": False},
        },
    }
    ch = build_free_fallback_chain(cfg)
    assert len(ch) == 1
    assert ch[0]["provider"] == "gemini"
    assert ch[0]["model"] == "gemma-4-31b-it"


def test_resolve_explicit_fallback_providers_wins():
    cfg = {
        "fallback_providers": [{"provider": "openai", "model": "gpt-4o"}],
        "free_model_routing": {"enabled": True, "kimi_router": {"router_model": "x", "tiers": [{"models": ["a"]}]}},
    }
    assert resolve_fallback_providers(cfg) == [{"provider": "openai", "model": "gpt-4o"}]


def test_resolve_explicit_plain_hf_dropped_for_gemini_synthesis():
    """Plain huggingface hub rows (no gemini_tier_router) are dropped — use Gemini synthesis."""
    cfg = {
        "fallback_providers": [
            {"provider": "huggingface", "model": "MiniMaxAI/MiniMax-M2.5"},
        ],
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "g", "models": ["some/hub-a"]}],
            },
            "openrouter_last_resort": {"enabled": False},
        },
    }
    out = resolve_fallback_providers(cfg)
    assert len(out) == 1
    assert out[0].get("gemini_tier_router") is True
    assert out[0]["provider"] == "gemini"
    assert out[0]["model"] == "gemma-4-31b-it"


def test_resolve_legacy_fallback_model_plain_hf_yields_to_gemini():
    cfg = {
        "fallback_model": {
            "provider": "huggingface",
            "model": "MiniMaxAI/MiniMax-M2.5",
        },
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "g", "models": ["some/hub-a"]}],
            },
        },
    }
    out = resolve_fallback_providers(cfg)
    assert out[0].get("gemini_tier_router") is True


def test_resolve_explicit_empty_list():
    cfg = {"fallback_providers": [], "free_model_routing": {"enabled": True}}
    assert resolve_fallback_providers(cfg) == []


def test_build_chain_gemini_direct():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "t", "models": ["org/a", "org/b"]}],
            },
            "openrouter_last_resort": {"enabled": False},
        },
    }
    ch = build_free_fallback_chain(cfg)
    assert len(ch) == 1
    assert ch[0]["gemini_tier_router"] is True
    assert ch[0]["provider"] == "gemini"
    assert ch[0]["model"] == "gemma-4-31b-it"


def test_openrouter_last_resort_appended_by_default():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "t", "models": ["org/a"]}],
            },
        },
    }
    ch = build_free_fallback_chain(cfg)
    assert len(ch) == 2
    assert ch[0]["provider"] == "gemini"
    assert ch[1]["provider"] == "openrouter"
    assert ch[1]["openrouter_last_resort"] is True
    assert ch[1]["only_rate_limit"] is True
    assert "gemma" in ch[1]["model"]


def test_openrouter_last_resort_disabled():
    cfg = {
        "free_model_routing": {
            "enabled": True,
            "kimi_router": {
                "router_model": "gemma-4-31b-it",
                "tiers": [{"id": "t", "models": ["org/a"]}],
            },
            "openrouter_last_resort": {"enabled": False},
        },
    }
    ch = build_free_fallback_chain(cfg)
    assert len(ch) == 1
    assert ch[0]["provider"] == "gemini"


def test_resolve_legacy_fallback_model_dict():
    cfg = {
        "fallback_model": {"provider": "zai", "model": "glm-9"},
    }
    assert resolve_fallback_providers(cfg) == [{"provider": "zai", "model": "glm-9"}]


# ── classify_model_cost provider-awareness ────────────────────────────


def test_classify_gemma_direct_gemini_is_free():
    from agent.subprocess_governance import classify_model_cost

    assert classify_model_cost("gemma-4-31b-it") == "free"
    assert classify_model_cost("gemma-4-31b-it", provider="gemini") == "free"


def test_classify_gemma_openrouter_is_low_cost():
    from agent.subprocess_governance import classify_model_cost

    assert classify_model_cost(
        "google/gemma-4-31b-it", provider="openrouter"
    ) == "low_cost"
    assert classify_model_cost(
        "gemma-4-31b-it", base_url="https://openrouter.ai/api/v1"
    ) == "low_cost"


def test_classify_openrouter_paid_model():
    from agent.subprocess_governance import classify_model_cost

    assert classify_model_cost(
        "anthropic/claude-sonnet-4.6", provider="openrouter"
    ) == "paid"
    assert classify_model_cost(
        "openai/gpt-5.4", base_url="https://openrouter.ai/api/v1"
    ) == "paid"
