"""Tests for automatic HR consultation hook."""

import unittest
from unittest.mock import MagicMock, patch

from agent.hr_consultation import (
    hr_consultation_triggers,
    maybe_append_hr_consultation,
)


class TestHrConsultationTriggers(unittest.TestCase):
    def test_disabled(self):
        self.assertFalse(
            hr_consultation_triggers("we need a new agent", {"enabled": False, "trigger_keywords": ["new agent"]})
        )

    def test_keyword_match(self):
        cfg = {"enabled": True, "trigger_keywords": ["new agent", "headcount"]}
        self.assertTrue(hr_consultation_triggers("Please add a new agent for billing", cfg))
        self.assertFalse(hr_consultation_triggers("Hello world", cfg))

    def test_min_message_chars(self):
        cfg = {"enabled": True, "trigger_keywords": ["x"], "min_message_chars": 100}
        self.assertFalse(hr_consultation_triggers("short x", cfg))


class TestMaybeAppendHrConsultation(unittest.TestCase):
    def test_subagent_skipped(self):
        agent = MagicMock()
        agent._delegate_depth = 1
        agent.valid_tool_names = ["delegate_task"]
        out = maybe_append_hr_consultation(
            agent,
            "new agent proposal",
            {"hr_consultation": {"enabled": True, "trigger_keywords": ["new agent"]}},
        )
        self.assertEqual(out, "new agent proposal")

    def test_no_delegate_tool(self):
        agent = MagicMock()
        agent._delegate_depth = 0
        agent.valid_tool_names = ["terminal"]
        out = maybe_append_hr_consultation(
            agent,
            "new agent proposal",
            {"hr_consultation": {"enabled": True, "trigger_keywords": ["new agent"]}},
        )
        self.assertEqual(out, "new agent proposal")

    @patch("tools.delegate_tool.delegate_task")
    def test_appends_summary(self, mock_delegate):
        mock_delegate.return_value = '{"results": [{"summary": "HR says wait for director."}]}'
        agent = MagicMock()
        agent._delegate_depth = 0
        agent.valid_tool_names = ["delegate_task", "terminal"]
        agent._emit_status = MagicMock()
        gov = {
            "hr_consultation": {
                "enabled": True,
                "trigger_keywords": ["new agent"],
                "hermes_profile": "ag-org-hr",
            }
        }
        out = maybe_append_hr_consultation(agent, "We need a new agent for ops", gov)
        self.assertIn("HR says wait", out)
        self.assertIn("We need a new agent", out)
        mock_delegate.assert_called_once()
        kw = mock_delegate.call_args.kwargs
        self.assertEqual(kw.get("hermes_profile"), "ag-org-hr")
