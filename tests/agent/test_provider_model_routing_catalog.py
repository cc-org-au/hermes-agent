"""Tests for provider_model_routing_catalog loading and prompt formatting."""

from __future__ import annotations

from agent import provider_model_routing_catalog as mod


def test_load_catalog_has_providers():
    data = mod.load_provider_model_routing_catalog()
    assert "providers" in data
    assert "openai" in data["providers"]
    assert len(data["providers"]["openai"]["models"]) >= 1


def test_digest_contains_openai_row_and_hints():
    text = mod.format_routing_catalog_digest()
    assert "gpt-5.4" in text
    assert "cross_provider_routing_hints" in text or "PROVIDER MODEL CATALOG" in text
    assert "MODEL_LINES_SORTED_CHEAPEST_FIRST" in text or "CHEAPEST-FIRST" in text


def test_digest_truncation():
    short = mod.format_routing_catalog_digest(max_chars=800)
    assert "PROVIDER MODEL CATALOG" in short
    assert "truncated" in short.lower()


def test_excludes_embedding_category():
    text = mod.format_routing_catalog_digest()
    assert "text-embedding-3-small" not in text
