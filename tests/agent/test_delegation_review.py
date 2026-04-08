"""Tests for agent/delegation_review.py — model gating for delegates."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.delegation_review import (
    gate_delegate_model,
    is_consultant_tier_model,
    review_delegation_context,
)


class TestIsConsultantTierModel:
    @pytest.mark.parametrize("model", [
        "anthropic/claude-opus-4.6",
        "gpt-5.4",
        "gpt-5.3-codex",
        "openai/gpt-5.4",
    ])
    def test_consultant_models(self, model):
        assert is_consultant_tier_model(model)

    @pytest.mark.parametrize("model", [
        "gemma-4-31b-it",
        "anthropic/claude-sonnet-4-6",
        "google/gemini-2.5-flash",
        "",
    ])
    def test_non_consultant_models(self, model):
        assert not is_consultant_tier_model(model)


class TestGateDelegateModel:
    def test_consultant_blocked(self):
        model, reason = gate_delegate_model("anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4-6")
        assert "opus" not in model.lower()
        assert "blocked" in reason

    def test_same_cost_approved(self):
        with patch("agent.subprocess_governance.classify_model_cost", return_value="free"):
            model, reason = gate_delegate_model("gemma-4-31b-it", "gemma-4-31b-it")
        assert model == "gemma-4-31b-it"
        assert reason == "approved"

    def test_more_expensive_downgraded(self):
        def mock_classify(mid):
            if "gemma" in mid:
                return "free"
            return "paid"

        with patch("agent.subprocess_governance.classify_model_cost", side_effect=mock_classify):
            model, reason = gate_delegate_model("anthropic/claude-sonnet-4-6", "gemma-4-31b-it")
        assert model != "anthropic/claude-sonnet-4-6"
        assert "downgraded" in reason or "expensive" in reason


class TestReviewDelegationContext:
    def test_empty_goal_skipped(self):
        result = review_delegation_context("", None, "gemma-4-31b-it")
        assert result["approved"] is True

    def test_fail_open_on_error(self):
        with patch("agent.auxiliary_client.call_llm", side_effect=RuntimeError("fail")):
            result = review_delegation_context("Fix the bug", "some context", "gemma-4-31b-it")
        assert result["approved"] is True

    def test_approved_response(self):
        with patch("agent.auxiliary_client.call_llm", return_value='{"approved": true}'):
            result = review_delegation_context("Fix the bug", "context", "gemma-4-31b-it")
        assert result["approved"] is True
