"""Gateway /profile-use and /profile-switch map to /profile (parity with CLI)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionEntry, SessionSource, build_session_key


def _source():
    return SessionSource(
        platform=Platform.SLACK,
        user_id="u1",
        chat_id="D1",
        user_name="t",
        chat_type="dm",
    )


@pytest.mark.asyncio
async def test_profile_use_no_args_becomes_profile_menu():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.SLACK: PlatformConfig(enabled=True, token="x")}
    )
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    se = SessionEntry(
        session_key=build_session_key(_source()),
        session_id="s",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.SLACK,
        chat_type="dm",
        total_tokens=0,
    )
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = se

    captured = {}

    async def _capture(self, event: MessageEvent) -> str:
        captured["text"] = event.text
        return "menu"

    with patch.object(GatewayRunner, "_handle_profile_command", _capture):
        ev = MessageEvent(
            text="/profile-switch",
            message_type=MessageType.COMMAND,
            source=_source(),
        )
        out = await GatewayRunner._handle_profile_use_command(runner, ev)

    assert out == "menu"
    assert captured["text"] == "/profile menu"


@pytest.mark.asyncio
async def test_profile_use_with_name_becomes_profile_use():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.SLACK: PlatformConfig(enabled=True, token="x")}
    )
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    captured = {}

    async def _capture(self, event: MessageEvent) -> str:
        captured["text"] = event.text
        return "use"

    with patch.object(GatewayRunner, "_handle_profile_command", _capture):
        ev = MessageEvent(
            text="/profile-use my-prof",
            message_type=MessageType.COMMAND,
            source=_source(),
        )
        out = await GatewayRunner._handle_profile_use_command(runner, ev)

    assert out == "use"
    assert captured["text"] == "/profile use my-prof"
