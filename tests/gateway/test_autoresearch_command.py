"""Tests for the gateway /autoresearch command flow."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _make_event(
    text="/autoresearch",
    platform=Platform.TELEGRAM,
    user_id="12345",
    chat_id="67890",
):
    source = SessionSource(
        platform=platform,
        user_id=user_id,
        chat_id=chat_id,
        user_name="testuser",
    )
    return MessageEvent(text=text, source=source)


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner._pending_autoresearch = {}
    runner._background_tasks = set()
    runner.session_store = MagicMock()
    runner._session_key_for_source = lambda _source: "sess_autoresearch"
    return runner


class TestGatewayAutoresearchCommand:
    def test_no_args_returns_clear_single_step_prompt(self):
        runner = _make_runner()
        event = _make_event(text="/autoresearch")

        result = asyncio.run(runner._handle_autoresearch_command(event))

        assert "only required interactive step" in result
        assert "very next message" in result
        assert "will not ask again" in result
        assert "sess_autoresearch" in runner._pending_autoresearch

    def test_show_returns_plain_paths(self):
        runner = _make_runner()
        event = _make_event(text="/autoresearch show")

        result = asyncio.run(runner._handle_autoresearch_command(event))

        assert "Autoresearch repo:" in result
        assert "Program file:" in result
        assert "`" not in result

    def test_inline_instructions_launch_background_run(self):
        runner = _make_runner()
        event = _make_event(text="/autoresearch improve safety")
        prepared = SimpleNamespace(
            job_id="autoresearch_123",
            program_path=Path("/tmp/program.md"),
            prompt_path=Path("/tmp/prompt.txt"),
            log_path=Path("/tmp/run.log"),
        )

        with patch(
            "hermes_cli.autoresearch_flow.prepare_autoresearch_background_run",
            return_value=prepared,
        ) as prepare_mock, patch.object(
            runner,
            "_start_autoresearch_background_run",
            AsyncMock(return_value="Autoresearch background run started."),
        ) as start_mock:
            result = asyncio.run(runner._handle_autoresearch_command(event))

        assert result == "Autoresearch background run started."
        prepare_mock.assert_called_once()
        start_mock.assert_awaited_once_with(
            event,
            prepared,
            "sess_autoresearch",
        )
