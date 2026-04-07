"""Tests for chief-orchestrator consultant routing (LLM router + deliberation)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agent.consultant_routing import (
    consultant_routing_enabled,
    governance_activation_signal,
    resolve_consultant_tier,
)


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    ops = home / "workspace" / "operations"
    ops.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_CONSULTANT_ROUTING_DISABLE", raising=False)
    return ops


def _gov_base():
    return {
        "enabled": True,
        "tier_models": {
            "B": "m-b",
            "C": "m-c",
            "D": "m-d",
            "E": "m-e",
            "F": "m-f",
        },
        "default_routing_tier": "D",
        "consultant_routing": {
            "enabled": True,
            "mode": "hybrid",
            "skip_router_when_tier_in": ["B"],
            "tiers_requiring_deliberation": ["E", "F"],
            "router_task": "consultant_router",
            "challenger_task": "consultant_challenger",
            "chief_task": "consultant_chief",
        },
    }


def test_governance_activation_signal_session_style_prompt():
    cr = {}
    blob = """
    Session 7 builds on Sessions 4 and 6. Activation protocol: Handoff before Verification.
    A. Outstanding tasks 1. REM-001: port 2. REM-002: browser
    ORG_REGISTRY.md ORG_CHART.md POLICY_ROOT governance role-prompts deployment order
    sub-agents verification executable
    """ * 6
    assert len(blob) >= 1600
    assert governance_activation_signal(blob, cr)


def test_governance_floor_forces_deliberation(monkeypatch, gov_env):
    g = _gov_base()
    g["consultant_routing"]["governance_activation_deliberation_floor"] = "E"

    def fake_call(task, system, user, max_tokens=512, *, agent=None):
        if "cost-aware" in system.lower() or "routing advisor" in system.lower():
            return json.dumps(
                {
                    "recommended_tier": "D",
                    "request_consultant_escalation": False,
                    "rationale": "stay cheap",
                }
            )
        if "challenge" in user.lower():
            return json.dumps({"challenge": "ok", "max_reasonable_tier": "E"})
        if "Chief Orchestrator" in system:
            return json.dumps(
                {
                    "approved_consultant_tier": True,
                    "final_tier": "E",
                    "decision_summary": "Activation session",
                }
            )
        return "{}"

    blob = (
        "Session 7 Activation protocol Handoff Verification ORG_REGISTRY ORG_CHART "
        "POLICY_ROOT governance REM-001 sub-agents deployment order executable "
        * 80
    )

    class _A:
        session_id = "s"

    with patch("agent.consultant_routing._call_aux_task", side_effect=fake_call):
        tier, audit = resolve_consultant_tier(blob, g, "D", g["tier_models"], agent=_A())
    assert audit.get("governance_activation_signal") is True
    assert audit.get("governance_deliberation_floor") == "E"
    assert tier == "E"


def test_consultant_disabled_without_nested_flag(gov_env):
    g = _gov_base()
    g["consultant_routing"]["enabled"] = False
    assert not consultant_routing_enabled(g)


def test_consultant_enabled(gov_env):
    assert consultant_routing_enabled(_gov_base())


def test_skip_router_when_deterministic_b(gov_env):
    g = _gov_base()
    tier, audit = resolve_consultant_tier(
        "summarize this",
        g,
        "B",
        g["tier_models"],
        agent=None,
    )
    assert tier == "B"
    assert audit.get("skipped_router") == "deterministic_tier_in_skip_list"


def test_hybrid_router_escalation_triggers_deliberation(gov_env):
    g = _gov_base()

    def fake_call(task, system, user, max_tokens=512, *, agent=None):
        if "routing advisor" in system.lower() or "cost-aware" in system.lower():
            return json.dumps(
                {
                    "recommended_tier": "F",
                    "request_consultant_escalation": True,
                    "rationale": "architecture review",
                }
            )
        if "challenge" in user.lower() or "Challenger" in system:
            return json.dumps(
                {"challenge": "try D first", "max_reasonable_tier": "D"}
            )
        if "Chief Orchestrator" in system:
            return json.dumps(
                {
                    "approved_consultant_tier": False,
                    "final_tier": "D",
                    "decision_summary": "Denied F; use D",
                }
            )
        return "{}"

    class _A:
        session_id = "sess-test"

    with patch("agent.consultant_routing._call_aux_task", side_effect=fake_call):
        tier, audit = resolve_consultant_tier(
            "Design the multi-region Kubernetes architecture for payments",
            g,
            "C",
            g["tier_models"],
            agent=_A(),
        )
    assert tier == "D"
    assert audit.get("deliberation") is not None


def test_deliberation_log_written(gov_env):
    g = _gov_base()
    log_path = gov_env / "consultant_deliberations.jsonl"

    def fake_call(task, system, user, max_tokens=512, *, agent=None):
        if "cost-aware" in system.lower() or "routing advisor" in system.lower():
            return json.dumps(
                {
                    "recommended_tier": "E",
                    "request_consultant_escalation": True,
                    "rationale": "need pro",
                }
            )
        if "challenge" in user.lower():
            return json.dumps({"challenge": "ok", "max_reasonable_tier": "E"})
        if "Chief Orchestrator" in system:
            return json.dumps(
                {
                    "approved_consultant_tier": True,
                    "final_tier": "E",
                    "decision_summary": "Approved E",
                }
            )
        return "{}"

    class _A:
        session_id = "sess-1"

    with patch("agent.consultant_routing._call_aux_task", side_effect=fake_call):
        tier, _ = resolve_consultant_tier(
            "x" * 500,
            g,
            "D",
            g["tier_models"],
            agent=_A(),
        )
    assert tier == "E"
    assert log_path.is_file()
    line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["final_tier"] == "E"
