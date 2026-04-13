"""Tests for daily budget ledger (routing_canon hard_budget)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.budget_ledger import (
    BudgetLedger,
    hours_until_local_midnight,
    hours_until_timezone_midnight,
)
from agent.routing_canon import load_hard_budget_config, invalidate_routing_canon_cache


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".hermes"
    h.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(h))
    invalidate_routing_canon_cache()
    yield h
    invalidate_routing_canon_cache()


def test_hours_until_midnight_positive():
    assert 0.0 <= hours_until_local_midnight() <= 24.0


def test_ledger_add_and_persist(home):
    p = home / "workspace" / "memory" / "runtime" / "operations" / "daily_budget_state.json"
    led = BudgetLedger(daily_budget_aud=10.0, aud_to_usd=0.65, path=p)
    assert led.daily_cap_usd == pytest.approx(6.5)
    led.add_spend_usd(0.1)
    assert led.spent_usd_today == pytest.approx(0.1)
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["spent_usd"] == pytest.approx(0.1)


def test_load_hard_budget_defaults(home):
    cfg = load_hard_budget_config()
    assert cfg["daily_budget_aud"] == 10.0
    assert cfg["enabled"] is True
    assert "Australia" in str(cfg.get("reset_timezone") or "")
    assert "operator_approval_when_daily_cap_exceeded" in cfg
    assert isinstance(cfg["operator_approval_when_daily_cap_exceeded"], bool)


def test_hours_until_timezone_midnight_reasonable():
    h = hours_until_timezone_midnight("Australia/Sydney")
    assert 0.0 <= h <= 24.0


def test_is_daily_exhausted(home):
    p = home / "workspace" / "memory" / "runtime" / "operations" / "daily_budget_state.json"
    led = BudgetLedger(daily_budget_aud=10.0, aud_to_usd=0.65, path=p)
    led.add_spend_usd(100.0)
    assert led.is_daily_exhausted()
