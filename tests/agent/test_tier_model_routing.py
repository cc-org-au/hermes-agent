"""Unit tests for tier letter selection (governance runtime heuristics)."""

from __future__ import annotations

import pytest

from agent.tier_model_routing import (
    resolve_tier_dynamic_model,
    select_tier_for_message,
)


def _base_cfg(**overrides):
    cfg = {
        "enabled": True,
        "tier_models": {
            "B": "m-b",
            "C": "m-c",
            "D": "m-d",
            "E": "m-e",
        },
        "chief_default_tier": "D",
        "default_routing_tier": "D",
    }
    cfg.update(overrides)
    return cfg


def test_select_summarize_still_tier_b():
    cfg = _base_cfg(dynamic_tier_routing=True)
    assert (
        select_tier_for_message("summarize the following paragraph in three bullets", cfg) == "B"
    )


def test_select_default_routing_chief_uses_chief_letter_for_fallback():
    cfg = _base_cfg(
        default_routing_tier="chief",
        chief_default_tier="E",
        dynamic_tier_routing=True,
    )
    # Does not match B/C: length > 900 so not in C's 120–900 window; fallback is chief → E
    msg = "x" * 1000
    assert select_tier_for_message(msg, cfg) == "E"


def test_select_default_routing_dynamic_length_bands():
    cfg = _base_cfg(
        default_routing_tier="dynamic",
        chief_default_tier="D",
        dynamic_fallback_medium_chars=500,
        dynamic_fallback_long_chars=2000,
        dynamic_fallback_medium_tier="C",
        dynamic_fallback_long_tier="E",
        dynamic_tier_routing=True,
    )
    # Short ambiguous: chief
    assert select_tier_for_message("x" * 100, cfg) == "D"
    # Medium
    assert select_tier_for_message("x" * 600, cfg) == "C"
    # Long
    assert select_tier_for_message("x" * 2500, cfg) == "E"


def test_select_dynamic_empty_message_is_chief():
    cfg = _base_cfg(default_routing_tier="dynamic", chief_default_tier="C")
    assert select_tier_for_message("", cfg) == "C"
    assert select_tier_for_message("   ", cfg) == "C"


def test_resolve_tier_dynamic_model_matches_select():
    cfg = _base_cfg(
        default_routing_tier="dynamic",
        chief_default_tier="D",
        dynamic_fallback_medium_chars=500,
        dynamic_fallback_long_chars=2000,
        dynamic_fallback_medium_tier="C",
        dynamic_fallback_long_tier="D",
    )
    assert resolve_tier_dynamic_model("x" * 600, cfg) == "m-c"
    assert resolve_tier_dynamic_model("x" * 100, cfg) == "m-d"


def test_incident_uses_base_default_when_incident_tier_unset():
    cfg = _base_cfg(
        default_routing_tier="chief",
        chief_default_tier="E",
    )
    msg = "production incident on checkout"
    assert select_tier_for_message(msg, cfg) == "E"


@pytest.mark.parametrize(
    "default_routing_tier,expected",
    [
        ("B", "B"),
        ("d", "D"),
    ],
)
def test_fixed_letter_fallback(default_routing_tier, expected):
    cfg = _base_cfg(default_routing_tier=default_routing_tier)
    msg = "hello world " * 200
    assert select_tier_for_message(msg, cfg) == expected
