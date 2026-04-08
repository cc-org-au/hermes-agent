"""Tests for agent/cost_monitor.py — spend rate tracking and circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from agent.cost_monitor import CostMonitor, load_cost_governance_config


class TestCostMonitor:
    def test_initial_ok(self):
        m = CostMonitor(session_budget_usd=5.0)
        assert m.record_cost(0.10) == "ok"
        assert not m.should_force_free_model()

    def test_budget_exceeded_triggers_circuit_break(self):
        m = CostMonitor(session_budget_usd=1.0)
        assert m.record_cost(1.01) == "circuit_break"
        assert m.should_force_free_model()

    def test_warn_at_80_percent(self):
        m = CostMonitor(session_budget_usd=1.0)
        assert m.record_cost(0.50) == "ok"
        assert m.record_cost(0.80) == "warn"
        # Subsequent calls below budget are ok (warn fires once)
        assert m.record_cost(0.85) == "ok"

    def test_spike_detection(self):
        m = CostMonitor(
            session_budget_usd=100.0,
            spike_threshold_usd_per_min=0.10,
        )
        now = time.monotonic()
        # Simulate rapid cost increase over 10 seconds
        with patch("agent.cost_monitor.time") as mock_time:
            mock_time.monotonic.return_value = now
            m.record_cost(0.0)
            mock_time.monotonic.return_value = now + 10.0
            result = m.record_cost(0.50)  # $0.50 in 10s = $3/min
        assert result == "circuit_break"
        assert m.should_force_free_model()

    def test_reset(self):
        m = CostMonitor(session_budget_usd=1.0)
        m.record_cost(1.5)
        assert m.should_force_free_model()
        m.reset()
        assert not m.should_force_free_model()

    def test_status_line(self):
        m = CostMonitor(session_budget_usd=2.50)
        line = m.status_line(0.75)
        assert "$0.750" in line
        assert "$2.50" in line

    def test_spend_rate_needs_data(self):
        m = CostMonitor()
        assert m.spend_rate_per_min() is None


class TestLoadCostGovernanceConfig:
    def test_defaults_when_none(self):
        cfg = load_cost_governance_config(None)
        assert cfg["daily_budget_usd"] == 10.0
        assert cfg["session_budget_usd"] == 2.50

    def test_overrides(self):
        gov = {"cost_governance": {"daily_budget_usd": 5.0, "session_budget_usd": 1.0}}
        cfg = load_cost_governance_config(gov)
        assert cfg["daily_budget_usd"] == 5.0
        assert cfg["session_budget_usd"] == 1.0

    def test_invalid_values_use_defaults(self):
        gov = {"cost_governance": {"daily_budget_usd": -1}}
        cfg = load_cost_governance_config(gov)
        assert cfg["daily_budget_usd"] == 10.0
