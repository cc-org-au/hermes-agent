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
    slash = m["features"]["slash_commands"]
    assert slash[0]["command"] == "/hermes"
    assert any(e.get("command") == "/hermes-help" for e in slash)
    assert len(slash) >= 30
    bot_scopes = set(m["oauth_config"]["scopes"]["bot"])
    assert "channels:manage" in bot_scopes
    assert "groups:write" in bot_scopes
    assert m["oauth_config"].get("redirect_urls") == [
        "https://localhost/slack/oauth_redirect"
    ]


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


def test_config_token_accepts_slack_manifest_key(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.delenv("SLACK_CONFIG_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_CONFIG_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_MANIFEST_KEY", "xoxe-test-token")
    assert sa._config_token_from_env() == "xoxe-test-token"


def test_config_token_from_get_env_value(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.delenv("SLACK_CONFIG_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_CONFIG_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_MANIFEST_KEY", raising=False)

    def fake_get_env(key: str):
        return "xoxe-from-file" if key == "SLACK_MANIFEST_KEY" else None

    monkeypatch.setattr("hermes_cli.config.get_env_value", fake_get_env)
    assert sa._config_token_from_env() == "xoxe-from-file"


def test_manifest_clone_split_tokens_uses_different_xoxe(monkeypatch, capsys):
    import hermes_cli.slack_admin as sa

    src_manifest = {
        "_metadata": {"major_version": 2},
        "display_information": {"name": "Hermes Agent"},
        "features": {"bot_user": {"display_name": "hermes"}},
        "settings": {"socket_mode_enabled": True},
    }
    calls = []

    def fake_api(method: str, token: str, **fields):
        calls.append((method, token))
        if method == "apps.manifest.export":
            assert token == "xoxe-droplet"
            return {"ok": True, "manifest": src_manifest}
        if method == "apps.manifest.validate":
            assert token == "xoxe-operator"
            return {"ok": True}
        if method == "apps.manifest.create":
            assert token == "xoxe-operator"
            return {
                "ok": True,
                "app_id": "A_SPLIT",
                "credentials": {},
                "oauth_authorize_url": "https://slack.com/oauth/…",
            }
        raise AssertionError(method)

    monkeypatch.setattr(sa, "_slack_tooling_api_with_token", fake_api)
    monkeypatch.setenv("SLACK_CONFIG_TOKEN_DROPLET", "xoxe-droplet")
    monkeypatch.setenv("SLACK_CONFIG_TOKEN_OPERATOR", "xoxe-operator")
    monkeypatch.delenv("SLACK_CONFIG_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_MANIFEST_KEY", raising=False)

    sa.slack_manifest_clone_from_app(
        source_app_id="A_OLD",
        new_display_name="hermes-operator",
    )
    assert [c[1] for c in calls] == [
        "xoxe-droplet",
        "xoxe-operator",
        "xoxe-operator",
    ]
    assert "new_app_id=A_SPLIT" in capsys.readouterr().out


def test_manifest_clone_only_droplet_token_errors(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.setenv("SLACK_CONFIG_TOKEN_DROPLET", "xoxe-only")
    monkeypatch.delenv("SLACK_CONFIG_TOKEN_OPERATOR", raising=False)
    monkeypatch.delenv("SLACK_CONFIG_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        sa.slack_manifest_clone_from_app(
            source_app_id="A_OLD",
            new_display_name="hermes-operator",
        )


def test_manifest_clone_calls_export_validate_create(monkeypatch, capsys):
    import hermes_cli.slack_admin as sa

    src_manifest = {
        "_metadata": {"major_version": 2},
        "display_information": {"name": "Hermes Agent"},
        "features": {"bot_user": {"display_name": "hermes"}},
        "settings": {"socket_mode_enabled": True},
    }
    calls = []

    def fake_api(method: str, token: str, **fields):
        calls.append((method, token, fields))
        if method == "apps.manifest.export":
            return {"ok": True, "manifest": src_manifest}
        if method == "apps.manifest.validate":
            m = fields.get("manifest")
            assert m and "hermes-operator" in m
            assert "Hermes Agent" not in m
            assert "localhost/slack/oauth_redirect" in m
            return {"ok": True}
        if method == "apps.manifest.create":
            return {
                "ok": True,
                "app_id": "A_NEW123",
                "credentials": {"client_id": "cid"},
                "oauth_authorize_url": "https://slack.com/oauth/…",
            }
        raise AssertionError(method)

    monkeypatch.setattr(sa, "_slack_tooling_api_with_token", fake_api)
    monkeypatch.setattr(
        sa,
        "_manifest_clone_tokens",
        lambda: ("xoxe-fake", "xoxe-fake", False),
    )

    sa.slack_manifest_clone_from_app(
        source_app_id="A_OLD",
        new_display_name="hermes-operator",
    )
    assert [c[0] for c in calls] == [
        "apps.manifest.export",
        "apps.manifest.validate",
        "apps.manifest.create",
    ]
    assert all(c[1] == "xoxe-fake" for c in calls)
    out = capsys.readouterr().out
    assert "new_app_id=A_NEW123" in out


def test_slack_command_manifest_patch_oauth_requires_confirm(monkeypatch):
    import hermes_cli.slack_admin as sa

    monkeypatch.setattr(sa, "slack_manifest_patch_oauth_install", lambda **kw: None)
    args = MagicMock(
        slack_command="manifest-patch-oauth",
        app_id="A1",
        confirm=False,
        bot_display_name=None,
        redirect_url=[],
    )
    with pytest.raises(SystemExit):
        sa.slack_command(args)


def test_slack_command_manifest_patch_oauth_dispatch(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_patch(**kw):
        called.update(kw)

    monkeypatch.setattr(sa, "slack_manifest_patch_oauth_install", fake_patch)
    args = MagicMock(
        slack_command="manifest-patch-oauth",
        app_id="A1",
        confirm=True,
        bot_display_name="hermes",
        redirect_url=["https://example.com/cb"],
    )
    sa.slack_command(args)
    assert called["app_id"] == "A1"
    assert called["bot_display_name"] == "hermes"
    assert called["extra_redirect_urls"] == ["https://example.com/cb"]


def test_slack_command_manifest_clone_dispatch(monkeypatch):
    import hermes_cli.slack_admin as sa

    called = {}

    def fake_clone(**kw):
        called.update(kw)

    monkeypatch.setattr(sa, "slack_manifest_clone_from_app", fake_clone)
    args = MagicMock(
        slack_command="manifest-clone",
        source_app_id="A1",
        new_name="hermes-operator",
        bot_display_name=None,
    )
    sa.slack_command(args)
    assert called["source_app_id"] == "A1"
    assert called["new_display_name"] == "hermes-operator"
    assert called["bot_display_name"] is None
