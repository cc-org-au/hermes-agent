"""HERMES_CRON_DELIVERY_DEDUPE overrides config for cron delivery dedupe."""

from __future__ import annotations

import pytest

from cron.delivery import cron_delivery_dedupe_enabled


def test_env_zero_disables_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_CRON_DELIVERY_DEDUPE", "0")
    assert cron_delivery_dedupe_enabled() is False


def test_env_false_disables_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_CRON_DELIVERY_DEDUPE", "false")
    assert cron_delivery_dedupe_enabled() is False


def test_env_unset_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_CRON_DELIVERY_DEDUPE", raising=False)
    assert isinstance(cron_delivery_dedupe_enabled(), bool)
