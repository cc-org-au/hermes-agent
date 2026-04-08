"""Tests for review_agent_summary() in agent/routing_engine.py."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agent.routing_engine import review_agent_summary


class TestReviewAgentSummary:
    def test_aligned_response(self):
        with patch("agent.auxiliary_client.call_llm", return_value='{"aligned": true}'):
            result = review_agent_summary(
                user_prompt_excerpt="How do I fix the auth bug?",
                agent_response_excerpt="The auth bug was caused by a missing token check. I've added validation.",
            )
        assert result["aligned"] is True

    def test_misaligned_response(self):
        resp = json.dumps({"aligned": False, "reason": "off topic", "action": "reroute"})
        with patch("agent.auxiliary_client.call_llm", return_value=resp):
            result = review_agent_summary(
                user_prompt_excerpt="Fix the database migration",
                agent_response_excerpt="The weather today is sunny.",
            )
        assert result["aligned"] is False
        assert "off topic" in result.get("reason", "")

    def test_empty_inputs_return_aligned(self):
        result = review_agent_summary("", "")
        assert result["aligned"] is True

    def test_fail_open_on_error(self):
        with patch("agent.auxiliary_client.call_llm", side_effect=RuntimeError("timeout")):
            result = review_agent_summary("prompt", "response")
        assert result["aligned"] is True

    def test_unparseable_response(self):
        with patch("agent.auxiliary_client.call_llm", return_value="not json at all"):
            result = review_agent_summary("prompt", "response")
        assert result["aligned"] is True
