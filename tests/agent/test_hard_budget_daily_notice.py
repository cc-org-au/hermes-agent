"""Hard budget user-visible notices (routing_canon) — no repeat spam per session/day."""

from __future__ import annotations

import pytest

from run_agent import AIAgent


@pytest.fixture
def agent(monkeypatch):
    a = AIAgent(quiet_mode=True, skip_context_files=True, skip_memory=True)
    a._hard_budget_operator_approval_required = False
    a._hard_budget_daily_cap_notice_emitted = False
    return a


def test_ledger_exhausted_switch_notice_emitted_once(agent):
    class Ledger:
        def is_daily_exhausted(self):
            return True

    agent._budget_ledger = Ledger()
    emitted: list[str] = []

    def _emit(msg, event_type="lifecycle"):
        emitted.append(msg)

    agent._emit_status = _emit
    agent._try_activate_fallback = lambda **kw: False
    agent._try_session_budget_cheaper_model = lambda: None

    agent._handle_hard_budget_ledger_exhausted_after_spend()
    agent._handle_hard_budget_ledger_exhausted_after_spend()
    agent._handle_hard_budget_ledger_exhausted_after_spend()

    assert len(emitted) == 1
    assert "routing_canon hard_budget" in emitted[0]
    assert agent._hard_budget_daily_cap_notice_emitted is True


def test_ledger_exhausted_operator_path_notice_once(agent):
    agent._hard_budget_operator_approval_required = True
    agent._hard_budget_operator_decision = None

    class Ledger:
        def is_daily_exhausted(self):
            return True

    agent._budget_ledger = Ledger()
    emitted: list[str] = []

    agent._emit_status = lambda msg, event_type="lifecycle": emitted.append(msg)

    agent._handle_hard_budget_ledger_exhausted_after_spend()
    agent._handle_hard_budget_ledger_exhausted_after_spend()

    assert len(emitted) == 1
    assert "approve or deny" in emitted[0]


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
