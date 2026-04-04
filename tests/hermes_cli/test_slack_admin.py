"""Tests for hermes_cli.slack_admin (no network)."""

from unittest.mock import MagicMock

import pytest


def test_tokens_from_env_missing_exits(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        sa._tokens_from_env()


def test_tokens_from_env_comma_separated(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-a, xoxb-b")
    assert sa._tokens_from_env() == ["xoxb-a", "xoxb-b"]


def test_slack_command_dispatches_join_public(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_join(*, dry_run=False):
        called["dry_run"] = dry_run

    monkeypatch.setattr(sa, "slack_join_public_channels", fake_join)
    args = MagicMock(slack_command="join-public", dry_run=True)
    sa.slack_command(args)
    assert called["dry_run"] is True


def test_slack_command_dispatches_whoami(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_whoami():
        called["ok"] = True

    monkeypatch.setattr(sa, "slack_whoami", fake_whoami)
    args = MagicMock(slack_command="whoami")
    sa.slack_command(args)
    assert called.get("ok") is True


def test_slack_command_dispatches_resolve_user(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_resolve(*, email=None, search=None):
        called["email"] = email
        called["search"] = search

    monkeypatch.setattr(sa, "slack_resolve_user", fake_resolve)
    args = MagicMock(
        slack_command="resolve-user",
        resolve_user_email="a@b.co",
        resolve_user_search=None,
    )
    sa.slack_command(args)
    assert called["email"] == "a@b.co"
    assert called["search"] is None


def test_hermes_slack_manifest_dict_shape():
    import hermes_cli.slack_admin as sa

    m = sa.hermes_slack_manifest_dict()
    assert m["_metadata"]["major_version"] == 2
    assert len(m["display_information"]["long_description"]) >= 174
    assert m["settings"]["socket_mode_enabled"] is True
    assert "message.channels" in m["settings"]["event_subscriptions"]["bot_events"]


def test_slack_command_manifest_validate_dispatch(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_validate(*, app_id=None):
        called["app_id"] = app_id

    monkeypatch.setattr(sa, "slack_manifest_validate", fake_validate)
    args = MagicMock(slack_command="manifest-validate", app_id="A0123")
    sa.slack_command(args)
    assert called["app_id"] == "A0123"


def test_slack_command_manifest_update_requires_confirm(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.setattr(sa, "slack_manifest_update", lambda **kw: None)
    args = MagicMock(slack_command="manifest-update", app_id="A1", confirm=False)
    with pytest.raises(SystemExit):
        sa.slack_command(args)
