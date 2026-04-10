"""Hard budget and budget_notice UX — once per logical session, registry-backed."""

from __future__ import annotations

import logging

import pytest

from pathlib import Path

from run_agent import (
    AIAgent,
    clear_budget_ux_notice_registry_entry,
    sync_budget_ux_notice_from_registry,
    _budget_ux_notice_by_session,
    _budget_ux_notice_lock,
    _quota_ux_registry_key,
)


@pytest.fixture
def agent(monkeypatch):
    a = AIAgent(quiet_mode=True, skip_context_files=True, skip_memory=True)
    a._hard_budget_operator_approval_required = False
    a.session_id = "sess_budget_ux"
    a._session_budget_ux_notice_done = False
    return a


def test_ledger_exhausted_switch_notice_emitted_once(agent, caplog):
    class Ledger:
        def is_daily_exhausted(self):
            return True

    agent._budget_ledger = Ledger()
    agent.platform = "telegram"
    with _budget_ux_notice_lock:
        clear_budget_ux_notice_registry_entry(agent)
    agent._try_activate_fallback = lambda **kw: False
    agent._try_session_budget_cheaper_model = lambda: None

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._handle_hard_budget_ledger_exhausted_after_spend()
        agent._handle_hard_budget_ledger_exhausted_after_spend()
        agent._handle_hard_budget_ledger_exhausted_after_spend()

    hard_lines = [
        r
        for r in caplog.records
        if "routing_canon hard_budget" in r.getMessage()
        and "suppressed" not in r.getMessage()
    ]
    assert len(hard_lines) == 1
    suppressed = [r for r in caplog.records if "budget_notice suppressed for session" in r.getMessage()]
    assert len(suppressed) >= 2


def test_budget_notice_gate_on_real_emit_status(agent, caplog):
    import logging

    agent.platform = "whatsapp"
    with _budget_ux_notice_lock:
        clear_budget_ux_notice_registry_entry(agent)
    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._emit_status("⚠️ first budget", event_type="budget_notice")
        agent._emit_status("⚠️ second budget", event_type="budget_notice")
    assert agent._session_budget_ux_notice_done is True
    assert not any(
        "second budget" in r.getMessage() and "suppressed" not in r.getMessage()
        for r in caplog.records
    )
    assert any("suppressed for session" in r.getMessage() for r in caplog.records)


def test_budget_notice_registry_survives_new_agent_same_session(tmp_path, monkeypatch, caplog):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    with _budget_ux_notice_lock:
        _budget_ux_notice_by_session.clear()
    a1 = AIAgent(quiet_mode=True, skip_context_files=True, skip_memory=True)
    a1.session_id = "gw_budget_sess"
    a1.platform = "telegram"
    with caplog.at_level(logging.INFO, logger="run_agent"):
        a1._emit_status("⚠️ cap", event_type="budget_notice")
    key = _quota_ux_registry_key(a1)
    assert _budget_ux_notice_by_session.get(key) is True
    a2 = AIAgent(quiet_mode=True, skip_context_files=True, skip_memory=True)
    a2.session_id = "gw_budget_sess"
    a2.platform = "telegram"
    sync_budget_ux_notice_from_registry(a2)
    assert a2._session_budget_ux_notice_done is True
    with caplog.at_level(logging.INFO, logger="run_agent"):
        a2._emit_status("⚠️ again", event_type="budget_notice")
    assert not any(
        "again" in r.getMessage() and "suppressed" not in r.getMessage() for r in caplog.records
    )
    assert any("suppressed for session" in r.getMessage() for r in caplog.records)


def test_ledger_exhausted_operator_path_notice_once(agent, caplog):
    agent._hard_budget_operator_approval_required = True
    agent._hard_budget_operator_decision = None

    class Ledger:
        def is_daily_exhausted(self):
            return True

    agent._budget_ledger = Ledger()
    agent.platform = "slack"
    with _budget_ux_notice_lock:
        clear_budget_ux_notice_registry_entry(agent)

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._handle_hard_budget_ledger_exhausted_after_spend()
        agent._handle_hard_budget_ledger_exhausted_after_spend()

    pause = [
        r
        for r in caplog.records
        if "approve or deny" in r.getMessage() and "suppressed" not in r.getMessage()
    ]
    assert len(pause) == 1


def test_ledger_exhausted_operator_approved_skips_notice_and_fallback(agent):
    from agent.budget_ledger import HARD_BUDGET_APPROVE_CHOICE

    agent._hard_budget_operator_approval_required = True
    agent._hard_budget_operator_decision = HARD_BUDGET_APPROVE_CHOICE

    class Ledger:
        def is_daily_exhausted(self):
            return True

    agent._budget_ledger = Ledger()
    agent._emit_status = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no emit"))
    agent._try_activate_fallback = lambda **kw: (_ for _ in ()).throw(
        AssertionError("no fallback when approved")
    )

    agent._handle_hard_budget_ledger_exhausted_after_spend()
