"""Tests for optional CLI profile routing (agent/profile_router.py)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_parse_router_json_raw():
    from agent.profile_router import _parse_router_json

    assert _parse_router_json('{"profile": "sec-guard", "confidence": 0.91, "reason": "x"}')[
        "profile"
    ] == "sec-guard"
    fenced = '```json\n{"profile": null, "confidence": 0.1}\n```'
    d = _parse_router_json(fenced)
    assert d is not None
    assert d.get("profile") is None


def test_list_routable_profile_names(tmp_path, monkeypatch):
    from agent import profile_router as pr

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".hermes" / "profiles"
    root.mkdir(parents=True)
    (root / "alpha-bot").mkdir()
    (root / "beta-bot").mkdir()
    assert pr.list_routable_profile_names() == ["alpha-bot", "beta-bot"]


def test_classify_skips_when_wrong_current_profile():
    from agent.profile_router import classify_profile_for_prompt

    t, _, reason = classify_profile_for_prompt(
        "hello world please route",
        candidates=["a"],
        current_profile="other",
        router_cfg={
            "only_when_current_profiles": ["chief-orchestrator"],
            "min_message_chars": 3,
        },
    )
    assert t is None
    assert "not in only_when_current" in reason


@patch("agent.profile_router.list_routable_profile_names", return_value=["worker"])
@patch("agent.auxiliary_client.extract_content_or_reasoning")
@patch("agent.auxiliary_client.call_llm")
def test_route_and_delegate_calls_delegate(mock_call, mock_extract, _lr):
    from agent.profile_router import route_and_delegate_if_configured

    mock_call.return_value = object()
    mock_extract.return_value = '{"profile": "worker", "confidence": 0.99, "reason": "ok"}'

    parent = MagicMock()
    with patch("tools.delegate_tool.delegate_task") as dt:
        dt.return_value = '{"results": [{"summary": "done"}], "total_duration_seconds": 1}'
        out = route_and_delegate_if_configured(
            user_message="do the security checklist",
            parent_agent=parent,
            agent_config={"enabled": True, "confidence_threshold": 0.5, "min_message_chars": 3},
            current_profile="chief-orchestrator",
        )
        assert out is not None
        assert "worker" in out
        assert "done" in out
        dt.assert_called_once()
        cargs, ckwargs = dt.call_args
        assert ckwargs.get("hermes_profile") == "worker"
