"""Tests for the /paperclip gateway slash command."""

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    runner.adapters = {}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = SessionEntry(
        session_key="agent:main:telegram:dm:c1:u1",
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.rewrite_transcript = MagicMock()
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._pending_autoresearch = {}
    runner._session_db = None
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._show_reasoning = False
    runner._is_user_authorized = lambda _source: True
    runner._set_session_env = lambda _context: None
    runner._run_agent = AsyncMock(
        return_value={
            "final_response": "paperclip-ready",
            "messages": [],
            "tools": [],
            "history_offset": 0,
            "last_prompt_tokens": 0,
        }
    )
    return runner


def _make_event(text="/paperclip"):
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.TELEGRAM,
            user_id="u1",
            chat_id="c1",
            user_name="tester",
            chat_type="dm",
        ),
        message_id="m1",
    )


def _make_paperclip_skills(skills_dir: Path) -> Path:
    repo_root = skills_dir / "external-repos" / "paperclip"
    for name, body in {
        "paperclip": "Coordinate Paperclip work.",
        "paperclip-create-agent": "Create Paperclip agents.",
        "paperclip-create-plugin": "Create Paperclip plugins.",
    }.items():
        skill_dir = repo_root / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"""---
name: {name}
description: Description for {name}.
---

# {name}

{body}
""",
            encoding="utf-8",
        )
    return repo_root


class TestGatewayPaperclipCommand:
    def test_paperclip_command_loads_skill_and_runs_agent(self, monkeypatch, tmp_path):
        import gateway.run as gateway_run

        runner = _make_runner()
        event = _make_event("/paperclip Review the current task queue")

        monkeypatch.setattr(
            gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"}
        )
        monkeypatch.setattr(
            "agent.model_metadata.get_model_context_length",
            lambda *_args, **_kwargs: 100_000,
        )

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: cfg)
            result = asyncio.run(runner._handle_message(event))

        assert result == "paperclip-ready"
        forwarded = runner._run_agent.call_args.kwargs["message"]
        assert 'The user has invoked the "paperclip" skill' in forwarded
        assert "Review the current task queue" in forwarded
        assert "pnpm paperclipai" in forwarded

    def test_paperclip_show_returns_plain_paths(self, monkeypatch, tmp_path):
        import gateway.run as gateway_run

        runner = _make_runner()
        event = _make_event("/paperclip show")

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: cfg)
            result = asyncio.run(runner._handle_message(event))

        assert "Paperclip repo:" in result
        assert "Paperclip skill:" in result
        assert "`" not in result

    def test_paperclip_agent_subcommand_routes_hidden_agent_skill(self, monkeypatch, tmp_path):
        import gateway.run as gateway_run

        runner = _make_runner()
        event = _make_event("/paperclip agent Make a CTO agent")

        monkeypatch.setattr(
            gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"}
        )
        monkeypatch.setattr(
            "agent.model_metadata.get_model_context_length",
            lambda *_args, **_kwargs: 100_000,
        )

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: cfg)
            result = asyncio.run(runner._handle_message(event))

        assert result == "paperclip-ready"
        forwarded = runner._run_agent.call_args.kwargs["message"]
        assert "paperclip-create-agent" in forwarded
        assert "Make a CTO agent" in forwarded
