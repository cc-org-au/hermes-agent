from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_cli.paperclip_flow import (
    PaperclipFlowError,
    build_paperclip_skill_message,
    format_paperclip_target_message,
    resolve_paperclip_repo_path,
    resolve_paperclip_skill_path,
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


def test_resolve_paperclip_paths_from_config(tmp_path):
    cfg = {"integrations": {"paperclip": {"repo": str(tmp_path)}}}

    assert resolve_paperclip_repo_path(cfg) == tmp_path
    assert resolve_paperclip_skill_path(cfg) == tmp_path / "skills" / "paperclip"


def test_format_paperclip_target_message_uses_plain_paths(tmp_path):
    cfg = {"integrations": {"paperclip": {"repo": str(tmp_path)}}}

    text = format_paperclip_target_message(cfg)

    assert "Paperclip repo:" in text
    assert "Paperclip skill:" in text
    assert "/paperclip agent" in text
    assert "`" not in text


def test_build_paperclip_skill_message_loads_nested_repo_skill(tmp_path):
    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        repo_root = _make_paperclip_skills(tmp_path)
        msg = build_paperclip_skill_message(
            user_instruction="Check the current Paperclip inbox.",
            config={"integrations": {"paperclip": {"repo": str(repo_root)}}},
        )

    assert "paperclip" in msg
    assert "Check the current Paperclip inbox." in msg
    assert "pnpm paperclipai" in msg
    assert str(repo_root) in msg


def test_build_paperclip_skill_message_routes_agent_subcommand(tmp_path):
    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        repo_root = _make_paperclip_skills(tmp_path)
        msg = build_paperclip_skill_message(
            user_instruction="agent Create a CTO agent",
            config={"integrations": {"paperclip": {"repo": str(repo_root)}}},
        )

    assert "paperclip-create-agent" in msg
    assert "Create a CTO agent" in msg
    assert "agent workflow" in msg


def test_build_paperclip_skill_message_raises_when_repo_missing(tmp_path):
    cfg = {"integrations": {"paperclip": {"repo": str(tmp_path / "missing")}}}

    with pytest.raises(PaperclipFlowError, match="Paperclip repo not found"):
        build_paperclip_skill_message(config=cfg)
