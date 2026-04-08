"""Tests for Slack channel and Telegram forum topic admin tools."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def hermes_home_env(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_slack_channel_admin_missing_token(hermes_home_env, monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    from tools.messaging_layout_tool import _slack_channel_admin_handler

    out = json.loads(_slack_channel_admin_handler({"action": "create", "name": "general"}))
    assert out.get("error")


def test_slack_channel_admin_create(hermes_home_env, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    from tools.messaging_layout_tool import _slack_channel_admin_handler

    mock_resp = MagicMock()
    mock_resp.data = {"ok": True, "channel": {"id": "C01234567", "name": "proj-alpha"}}

    with patch("slack_sdk.WebClient") as WC:
        WC.return_value.conversations_create.return_value = mock_resp
        out = json.loads(_slack_channel_admin_handler({"action": "create", "name": "proj-alpha"}))

    assert out.get("ok") is True
    assert out.get("channel", {}).get("id") == "C01234567"
    WC.return_value.conversations_create.assert_called_once()
    call_kw = WC.return_value.conversations_create.call_args[1]
    assert call_kw["name"] == "proj-alpha"
    assert call_kw["is_private"] is False


def test_slack_channel_admin_invalid_action(hermes_home_env, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    from tools.messaging_layout_tool import _slack_channel_admin_handler

    out = json.loads(_slack_channel_admin_handler({"action": "nope"}))
    assert "error" in out


def test_telegram_forum_topic_missing_token(hermes_home_env, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from tools.messaging_layout_tool import _telegram_forum_topic_handler

    out = json.loads(
        _telegram_forum_topic_handler({"action": "create", "chat_id": -100123, "name": "T1"})
    )
    assert out.get("error") or out.get("ok") is False


def test_telegram_forum_topic_create(hermes_home_env, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"ok":true,"result":{"message_thread_id":42,"name":"T1"}}'

    from tools.messaging_layout_tool import _telegram_forum_topic_handler

    with patch("urllib.request.urlopen", return_value=_Resp()):
        out = json.loads(
            _telegram_forum_topic_handler(
                {"action": "create", "chat_id": -1003348811704, "name": "T1"}
            )
        )

    assert out.get("ok") is True
    assert out.get("result", {}).get("message_thread_id") == 42


def test_telegram_forum_topic_edit_requires_field(hermes_home_env, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:FAKE")
    from tools.messaging_layout_tool import _telegram_forum_topic_handler

    out = json.loads(
        _telegram_forum_topic_handler(
            {"action": "edit", "chat_id": -100, "message_thread_id": 7}
        )
    )
    assert "error" in out


def test_check_functions(hermes_home_env, monkeypatch):
    from tools.messaging_layout_tool import _check_slack_token, _check_telegram_token

    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert _check_slack_token() is False
    assert _check_telegram_token() is False

    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "y")
    assert _check_slack_token() is True
    assert _check_telegram_token() is True
