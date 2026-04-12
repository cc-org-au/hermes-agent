"""REM-003: optional channel / workspace allowlists for non-DM gateway surfaces."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.session import SessionSource


def _clear_surface_env(monkeypatch) -> None:
    for key in (
        "TELEGRAM_ALLOWED_CHATS",
        "DISCORD_ALLOWED_CHANNELS",
        "DISCORD_ALLOWED_GUILDS",
        "SLACK_ALLOWED_CHANNELS",
        "SLACK_ALLOWED_TEAMS",
        "SLACK_ALLOWED_WORKSPACE_TEAMS",
        "WHATSAPP_ALLOWED_CHATS",
    ):
        monkeypatch.delenv(key, raising=False)


def _make_runner(platform: Platform):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(platforms={platform: PlatformConfig(enabled=True)})
    runner.adapters = {platform: SimpleNamespace(send=AsyncMock())}
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    return runner


def test_dm_bypasses_discord_channel_list(monkeypatch):
    _clear_surface_env(monkeypatch)
    monkeypatch.setenv("DISCORD_ALLOWED_USERS", "111")
    monkeypatch.setenv("DISCORD_ALLOWED_CHANNELS", "999999")

    runner = _make_runner(Platform.DISCORD)
    src = SessionSource(
        platform=Platform.DISCORD,
        user_id="111",
        chat_id="dm-channel",
        chat_type="dm",
        server_id="55",
    )
    assert runner._is_user_authorized(src) is True


def test_discord_group_denied_when_channel_not_listed(monkeypatch):
    _clear_surface_env(monkeypatch)
    monkeypatch.setenv("DISCORD_ALLOWED_USERS", "111")
    monkeypatch.setenv("DISCORD_ALLOWED_CHANNELS", "999999")

    runner = _make_runner(Platform.DISCORD)
    src = SessionSource(
        platform=Platform.DISCORD,
        user_id="111",
        chat_id="888888",
        chat_type="group",
        server_id="55",
    )
    assert runner._is_user_authorized(src) is False


def test_discord_guild_fallback_when_channels_wrong(monkeypatch):
    _clear_surface_env(monkeypatch)
    monkeypatch.setenv("DISCORD_ALLOWED_USERS", "111")
    monkeypatch.setenv("DISCORD_ALLOWED_CHANNELS", "999999")
    monkeypatch.setenv("DISCORD_ALLOWED_GUILDS", "55")

    runner = _make_runner(Platform.DISCORD)
    src = SessionSource(
        platform=Platform.DISCORD,
        user_id="111",
        chat_id="888888",
        chat_type="group",
        server_id="55",
    )
    assert runner._is_user_authorized(src) is True


def test_slack_team_only_allowlist(monkeypatch):
    _clear_surface_env(monkeypatch)
    monkeypatch.setenv("SLACK_ALLOWED_USERS", "U111")
    monkeypatch.setenv("SLACK_ALLOWED_TEAMS", "T09ABCDEF")

    runner = _make_runner(Platform.SLACK)
    ok = SessionSource(
        platform=Platform.SLACK,
        user_id="U111",
        chat_id="CZZZZZZ",
        chat_type="group",
        server_id="T09ABCDEF",
    )
    bad = SessionSource(
        platform=Platform.SLACK,
        user_id="U111",
        chat_id="CZZZZZZ",
        chat_type="group",
        server_id="T_OTHER___",
    )
    assert runner._is_user_authorized(ok) is True
    assert runner._is_user_authorized(bad) is False


def test_slack_workspace_teams_env_alias(monkeypatch):
    """CHANNEL_ARCHITECTURE uses SLACK_ALLOWED_WORKSPACE_TEAMS — same as SLACK_ALLOWED_TEAMS."""
    _clear_surface_env(monkeypatch)
    monkeypatch.setenv("SLACK_ALLOWED_USERS", "U111")
    monkeypatch.setenv("SLACK_ALLOWED_WORKSPACE_TEAMS", "T09ABCDEF")
    monkeypatch.delenv("SLACK_ALLOWED_TEAMS", raising=False)

    runner = _make_runner(Platform.SLACK)
    ok = SessionSource(
        platform=Platform.SLACK,
        user_id="U111",
        chat_id="CZZZZZZ",
        chat_type="group",
        server_id="T09ABCDEF",
    )
    assert runner._is_user_authorized(ok) is True
