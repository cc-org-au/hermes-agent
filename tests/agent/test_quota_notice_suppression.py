"""Session-scoped suppression of user-visible quota/rate-limit notices."""

from __future__ import annotations

import pytest

from run_agent import AIAgent


@pytest.fixture
def agent():
    a = AIAgent(quiet_mode=True, skip_context_files=True, skip_memory=True)
    a.session_id = "test_sess_quota"
    return a


def test_quota_notice_resets_when_session_id_changes(agent):
    agent._quota_notice_session_id = "old"
    agent._session_suppress_quota_user_notices = True

    # Simulate run_conversation header logic
    agent.session_id = "new_sess"
    _q_sid = str(getattr(agent, "session_id", "") or "")
    _prev_q = getattr(agent, "_quota_notice_session_id", None)
    if _prev_q is not None and _prev_q != _q_sid:
        agent._session_suppress_quota_user_notices = False
    agent._quota_notice_session_id = _q_sid

    assert agent._session_suppress_quota_user_notices is False
    assert agent._quota_notice_session_id == "new_sess"


def test_emit_quota_user_notice_suppressed_after_flag(agent, caplog):
    import logging

    agent._session_suppress_quota_user_notices = True
    emitted = []

    def _cb(et, msg):
        emitted.append((et, msg))

    agent.status_callback = _cb
    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._emit_quota_user_notice("⚠️ Quota test", "lifecycle")
    assert emitted == []
    assert any("quota user notice suppressed" in r.getMessage() for r in caplog.records)


def test_session_note_quota_exhausted_sets_flag(agent):
    agent._opm_qf_phase = "or_done"
    agent._session_suppress_quota_user_notices = False
    agent._session_note_quota_cascade_exhausted_if_applicable()
    assert agent._session_suppress_quota_user_notices is True
