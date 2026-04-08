"""Tests for Claude Opus 4.6 (tier G) escalation gate."""

from __future__ import annotations

from agent.tier_model_routing import BUILTIN_TIER_MODELS, TIER_SENTINEL_RE


class TestTierGPresent:
    def test_tier_g_in_builtin(self):
        assert "G" in BUILTIN_TIER_MODELS
        assert "opus" in BUILTIN_TIER_MODELS["G"].lower()

    def test_tier_sentinel_regex_matches_g(self):
        assert TIER_SENTINEL_RE.match("tier:G")
        assert TIER_SENTINEL_RE.match("tier:g")

    def test_tier_sentinel_regex_still_matches_af(self):
        for letter in "ABCDEF":
            assert TIER_SENTINEL_RE.match(f"tier:{letter}")
