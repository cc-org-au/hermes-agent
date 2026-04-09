"""Tests for agent/provider_health.py — session-scoped provider blacklisting."""

from __future__ import annotations

import pytest

from agent.provider_health import ProviderHealthTracker


class TestProviderHealthTracker:
    def test_initial_state(self):
        t = ProviderHealthTracker()
        assert not t.is_blacklisted("openai")
        assert t.summary() == {"failures": {}, "blacklisted": []}

    def test_blacklist_after_three_failures(self):
        t = ProviderHealthTracker()
        assert not t.record_failure("openai", "500")
        assert not t.record_failure("openai", "500")
        assert t.record_failure("openai", "500")
        assert t.is_blacklisted("openai")

    def test_huggingface_blacklist_after_one(self):
        t = ProviderHealthTracker()
        assert t.record_failure("huggingface", "401")
        assert t.is_blacklisted("huggingface")

    def test_success_resets_counter(self):
        t = ProviderHealthTracker()
        t.record_failure("openai", "429")
        t.record_failure("openai", "429")
        t.record_success("openai")
        assert not t.record_failure("openai", "429")
        assert not t.is_blacklisted("openai")

    def test_success_does_not_unblacklist(self):
        t = ProviderHealthTracker(default_max_failures=1)
        t.record_failure("openai", "500")
        assert t.is_blacklisted("openai")
        t.record_success("openai")
        assert t.is_blacklisted("openai")

    def test_reset_clears_everything(self):
        t = ProviderHealthTracker()
        for _ in range(3):
            t.record_failure("openai")
        assert t.is_blacklisted("openai")
        t.reset()
        assert not t.is_blacklisted("openai")
        assert t.summary() == {"failures": {}, "blacklisted": []}

    def test_custom_overrides(self):
        t = ProviderHealthTracker(overrides={"gemini": 5})
        for i in range(4):
            assert not t.record_failure("gemini")
        assert t.record_failure("gemini")
        assert t.is_blacklisted("gemini")

    def test_case_insensitive(self):
        t = ProviderHealthTracker()
        t.record_failure("OpenAI")
        t.record_failure("OPENAI")
        assert t.record_failure("openai")
        assert t.is_blacklisted("OpenAI")

    def test_blacklist_reason(self):
        t = ProviderHealthTracker()
        for _ in range(3):
            t.record_failure("openai", "HTTP 500")
        reason = t.blacklist_reason("openai")
        assert "3 consecutive failures" in reason
        assert "HTTP 500" in reason

    def test_empty_provider_ignored(self):
        t = ProviderHealthTracker()
        assert not t.record_failure("")
        assert not t.is_blacklisted("")

    def test_already_blacklisted_returns_false(self):
        """Subsequent record_failure must not look like a fresh blacklist event."""
        t = ProviderHealthTracker(default_max_failures=1)
        assert t.record_failure("openai", "500")
        assert t.is_blacklisted("openai")
        assert not t.record_failure("openai", "500")
        assert not t.record_failure("openai", "500")
