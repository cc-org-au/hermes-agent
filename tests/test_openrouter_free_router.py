"""Tests for synthetic ``openrouter/free`` resolution."""

from __future__ import annotations

import pytest

from agent.openrouter_free_router import (
    OPENROUTER_FREE_SYNTHETIC,
    OpenRouterFreeResolutionError,
    clear_openrouter_free_cache_for_tests,
    pick_free_slug,
    resolve_openrouter_free_model_for_api,
)


def test_pick_free_slug_capability_score_order():
    candidates = ["b:free", "a:free"]
    live = ["a:free", "b:free"]
    scores = {"a:free": 10, "b:free": 50}
    assert pick_free_slug(candidates, live, ranking="capability_score", scores=scores) == "b:free"


def test_pick_free_slug_cheapest_first():
    candidates = ["z:free", "a:free"]
    live = ["z:free", "a:free"]
    assert (
        pick_free_slug(candidates, live, ranking="cheapest_first", scores={}) == "z:free"
    )


def test_resolve_openrouter_free_success(monkeypatch):
    clear_openrouter_free_cache_for_tests()

    def _cfg():
        return {
            "enabled": True,
            "api_use_native_free_router": False,
            "strict_no_paid_fallback": True,
            "ranking": "capability_score",
            "live_fetch_ttl_seconds": 3600,
            "empty_error_message": "empty",
            "candidate_slugs": ["m1:free", "m2:free"],
            "capability_scores": {"m1:free": 10, "m2:free": 20},
        }

    monkeypatch.setattr("agent.routing_canon.load_openrouter_free_router_config", _cfg)
    monkeypatch.setattr(
        "agent.openrouter_free_router.get_openrouter_free_model_ids_cached",
        lambda *a, **k: ["m1:free", "m2:free"],
    )
    out = resolve_openrouter_free_model_for_api(
        configured_model=OPENROUTER_FREE_SYNTHETIC,
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
    )
    assert out == "m2:free"


def test_resolve_openrouter_free_empty_intersection(monkeypatch):
    clear_openrouter_free_cache_for_tests()

    def _cfg():
        return {
            "enabled": True,
            "api_use_native_free_router": False,
            "candidate_slugs": ["only-paid/model"],
            "capability_scores": {},
            "ranking": "capability_score",
            "live_fetch_ttl_seconds": 3600,
            "empty_error_message": "no free match",
        }

    monkeypatch.setattr("agent.routing_canon.load_openrouter_free_router_config", _cfg)
    monkeypatch.setattr(
        "agent.openrouter_free_router.get_openrouter_free_model_ids_cached",
        lambda *a, **k: ["other:free"],
    )
    with pytest.raises(OpenRouterFreeResolutionError, match="no free match"):
        resolve_openrouter_free_model_for_api(
            configured_model=OPENROUTER_FREE_SYNTHETIC,
            api_key="k",
            base_url="https://openrouter.ai/api/v1",
        )


def test_resolve_non_synthetic_passthrough():
    clear_openrouter_free_cache_for_tests()
    assert (
        resolve_openrouter_free_model_for_api(
            configured_model="anthropic/claude-3-haiku",
            api_key="",
            base_url="",
        )
        == "anthropic/claude-3-haiku"
    )


def test_resolve_openrouter_free_default_uses_native_router_string(monkeypatch):
    """Default canon passes through ``openrouter/free`` (OpenRouter Free Models Router)."""
    clear_openrouter_free_cache_for_tests()

    def _cfg():
        return {
            "enabled": True,
            "api_use_native_free_router": True,
            "strict_no_paid_fallback": True,
            "ranking": "capability_score",
            "live_fetch_ttl_seconds": 3600,
            "empty_error_message": "empty",
            "candidate_slugs": ["m1:free"],
            "capability_scores": {},
        }

    monkeypatch.setattr("agent.routing_canon.load_openrouter_free_router_config", _cfg)
    out = resolve_openrouter_free_model_for_api(
        configured_model=OPENROUTER_FREE_SYNTHETIC,
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
    )
    assert out == OPENROUTER_FREE_SYNTHETIC
