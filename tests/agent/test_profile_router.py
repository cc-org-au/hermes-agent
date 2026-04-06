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


@patch("agent.profile_router._call_profile_router_llm")
@patch("agent.auxiliary_client.extract_content_or_reasoning")
def test_classify_success_when_profile_router_llm_returns_json(mock_extract, mock_pr_llm):
    from agent.profile_router import classify_profile_for_prompt

    mock_pr_llm.return_value = object()
    mock_extract.return_value = '{"profile": "sec-bot", "confidence": 0.95, "reason": "ok"}'

    t, conf, _reason = classify_profile_for_prompt(
        "full security posture audit please",
        candidates=["sec-bot", "other"],
        current_profile="chief-orchestrator",
        router_cfg={
            "only_when_current_profiles": ["chief-orchestrator"],
            "min_message_chars": 3,
            "confidence_threshold": 0.72,
        },
    )
    assert t == "sec-bot"
    assert conf == 0.95
    mock_pr_llm.assert_called_once()


@patch("agent.profile_router._call_profile_router_llm", side_effect=RuntimeError("no HF token"))
@patch("agent.auxiliary_client.extract_content_or_reasoning")
def test_classify_returns_error_when_profile_router_llm_raises(_mock_extract, _mock_pr_llm):
    from agent.profile_router import classify_profile_for_prompt

    t, conf, reason = classify_profile_for_prompt(
        "full security posture audit please",
        candidates=["sec-bot", "other"],
        current_profile="chief-orchestrator",
        router_cfg={
            "only_when_current_profiles": ["chief-orchestrator"],
            "min_message_chars": 3,
            "confidence_threshold": 0.72,
        },
    )
    assert t is None
    assert conf == 0.0
    assert "router error" in reason


@patch("agent.profile_router.list_routable_profile_names", return_value=["worker"])
@patch("agent.profile_router._call_profile_router_llm")
@patch("agent.auxiliary_client.extract_content_or_reasoning")
def test_route_and_delegate_uses_precomputed_skips_classify(mock_extract, mock_pr_llm, _lr):
    from agent.profile_router import classify_profile_for_prompt, route_and_delegate_if_configured

    mock_pr_llm.return_value = object()
    mock_extract.return_value = '{"profile": "worker", "confidence": 0.99, "reason": "ok"}'

    parent = MagicMock()
    with patch("tools.delegate_tool.delegate_task") as dt:
        dt.return_value = '{"results": [{"summary": "done"}], "total_duration_seconds": 1}'
        out = route_and_delegate_if_configured(
            user_message="x",
            parent_agent=parent,
            agent_config={"enabled": True, "confidence_threshold": 0.5, "min_message_chars": 3},
            current_profile="chief-orchestrator",
            precomputed=("worker", 0.99, "ok"),
        )
        assert out is not None
        dt.assert_called_once()
    mock_pr_llm.assert_not_called()


@patch("agent.profile_router.list_routable_profile_names", return_value=["worker"])
@patch("agent.profile_router._call_profile_router_llm")
@patch("agent.auxiliary_client.extract_content_or_reasoning")
def test_route_and_delegate_calls_delegate(mock_extract, mock_pr_llm, _lr):
    from agent.profile_router import route_and_delegate_if_configured

    mock_pr_llm.return_value = object()
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


def test_classify_keyword_project_lead_skips_llm():
    from agent.profile_router import classify_profile_for_prompt

    with patch("agent.auxiliary_client.call_llm") as mock_call:
        t, conf, reason = classify_profile_for_prompt(
            "can i get a status update from the project lead for the agentic-company project?",
            candidates=["chief-orchestrator", "ag-pl-agentic-company", "fd-product"],
            current_profile="chief-orchestrator",
            router_cfg={
                "only_when_current_profiles": ["chief-orchestrator"],
                "min_message_chars": 3,
                "confidence_threshold": 0.65,
            },
        )
    assert mock_call.call_count == 0
    assert t == "ag-pl-agentic-company"
    assert conf >= 0.65
    assert "project-lead" in reason.lower()


def test_classify_keyword_security_skips_llm():
    from agent.profile_router import classify_profile_for_prompt

    with patch("agent.auxiliary_client.call_llm") as mock_call:
        t, conf, reason = classify_profile_for_prompt(
            "what is my security posture today?",
            candidates=["ag-sec-preflight", "other-bot"],
            current_profile="chief-orchestrator",
            router_cfg={
                "only_when_current_profiles": ["chief-orchestrator"],
                "min_message_chars": 3,
                "confidence_threshold": 0.65,
            },
        )
    assert mock_call.call_count == 0
    assert t == "ag-sec-preflight"
    assert conf >= 0.65
    assert "keyword" in reason.lower()


def test_call_profile_router_llm_uses_kimi_tier_pick(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token-for-test")
    from agent import profile_router as pr

    fake_fmr = {
        "enabled": True,
        "kimi_router": {
            "router_model": "moonshotai/Kimi-K2-Thinking",
            "tiers": [
                {"id": "general", "description": "g", "models": ["some/hub-id"]},
            ],
        },
    }

    with patch("hermes_cli.config.load_config", return_value={"free_model_routing": fake_fmr}), patch(
        "agent.hf_fallback_router.resolve_hf_routed_model",
        return_value="kimi-picked-hub-model",
    ) as mock_resolve, patch("agent.auxiliary_client.call_llm") as mock_llm:
        mock_llm.return_value = object()
        pr._call_profile_router_llm(
            [{"role": "user", "content": "route me"}],
            {"use_free_model_routing": True},
        )
    mock_resolve.assert_called_once()
    mock_llm.assert_called_once()
    assert mock_llm.call_args.kwargs.get("model") == "kimi-picked-hub-model"
