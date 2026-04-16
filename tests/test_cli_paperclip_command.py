"""Tests for the /paperclip CLI slash command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from cli import HermesCLI


def _make_cli():
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.config = {}
    cli_obj.console = MagicMock()
    cli_obj.agent = None
    cli_obj.conversation_history = []
    cli_obj.session_id = "sess-paperclip"
    cli_obj._pending_input = MagicMock()
    return cli_obj


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


class TestCLIPaperclipCommand:
    def test_paperclip_command_queues_skill_message(self, tmp_path):
        cli_obj = _make_cli()

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            with patch("cli.load_cli_config", return_value=cfg):
                result = cli_obj.process_command("/paperclip Check the inbox")

        assert result is True
        cli_obj._pending_input.put.assert_called_once()
        queued = cli_obj._pending_input.put.call_args[0][0]
        assert 'The user has invoked the "paperclip" skill' in queued
        assert "Check the inbox" in queued
        assert str(repo_root) in queued

    def test_paperclip_without_args_uses_default_session_brief(self, tmp_path):
        cli_obj = _make_cli()

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            with patch("cli.load_cli_config", return_value=cfg):
                cli_obj.process_command("/paperclip")

        queued = cli_obj._pending_input.put.call_args[0][0]
        assert "Start a Paperclip coordination session now." in queued
        assert "most relevant next action" in queued

    def test_paperclip_agent_subcommand_queues_agent_skill(self, tmp_path):
        cli_obj = _make_cli()

        with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
            repo_root = _make_paperclip_skills(tmp_path)
            cfg = {"integrations": {"paperclip": {"repo": str(repo_root)}}}
            with patch("cli.load_cli_config", return_value=cfg):
                cli_obj.process_command("/paperclip agent Make a CTO agent")

        queued = cli_obj._pending_input.put.call_args[0][0]
        assert "paperclip-create-agent" in queued
        assert "Make a CTO agent" in queued
