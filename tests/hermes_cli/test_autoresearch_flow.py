from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hermes_cli.autoresearch_flow import (
    append_and_build_autoresearch_skill_message,
    append_autoresearch_instructions,
    build_autoresearch_worker_command,
    format_autoresearch_capture_prompt,
    prepare_autoresearch_background_run,
    resolve_autoresearch_program_path,
)


def test_resolve_autoresearch_program_path_defaults_to_profile_skill_repo(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    program_path = resolve_autoresearch_program_path()

    assert program_path == hermes_home / "skills" / "external-repos" / "autoresearch" / "program.md"


def test_append_autoresearch_instructions_appends_managed_block(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    repo = hermes_home / "skills" / "external-repos" / "autoresearch"
    repo.mkdir(parents=True)
    program_path = repo / "program.md"
    program_path.write_text("# autoresearch\n\nBase upstream content.\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    result = append_autoresearch_instructions("Focus on better CPU throughput.")

    updated = program_path.read_text(encoding="utf-8")
    assert result.program_path == program_path
    assert "Base upstream content." in updated
    assert "Focus on better CPU throughput." in updated
    assert "HERMES_AUTORESEARCH_INSTRUCTIONS_START" in updated
    assert "Repository target: `efecanbasoz/autoresearch-cpu`" in updated
    assert "default to 30 minutes total for the outer loop" in updated


def test_capture_prompt_mentions_program_path(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    text = format_autoresearch_capture_prompt()

    assert "program.md" in text
    assert "only required interactive step" in text
    assert "will not ask again" in text
    assert "total outer runtime" in text
    assert "default to 30 minutes total" in text
    assert "/autoresearch cancel" in text


def test_append_and_build_message_loads_hidden_autoresearch_skill(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    repo = hermes_home / "skills" / "external-repos" / "autoresearch"
    repo.mkdir(parents=True)
    (repo / "program.md").write_text("# autoresearch\n", encoding="utf-8")
    (repo / "SKILL.md").write_text(
        """\
---
name: autoresearch
description: Run the autoresearch workflow.
---

# autoresearch

Follow the repo instructions.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with patch("tools.skills_tool.SKILLS_DIR", hermes_home / "skills"):
        result, msg = append_and_build_autoresearch_skill_message(
            user_instructions="Focus on CPU throughput."
        )

    updated = (repo / "program.md").read_text(encoding="utf-8")
    assert result.program_path == repo / "program.md"
    assert "HERMES_AUTORESEARCH_INSTRUCTIONS_START" in updated
    assert "Focus on CPU throughput." in updated
    assert "Read the repo's `program.md`" in msg
    assert "Runtime note:" in msg


def test_prepare_background_run_writes_prompt_and_log_paths(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes" / "profiles" / "chief-orchestrator"
    repo = hermes_home / "skills" / "external-repos" / "autoresearch"
    repo.mkdir(parents=True)
    (repo / "program.md").write_text("# autoresearch\n", encoding="utf-8")
    (repo / "SKILL.md").write_text(
        """\
---
name: autoresearch
description: Run the autoresearch workflow.
---

# autoresearch

Follow the repo instructions.
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with patch("tools.skills_tool.SKILLS_DIR", hermes_home / "skills"):
        prepared = prepare_autoresearch_background_run(
            user_instructions="Focus on safer subprocess behavior."
        )

    assert prepared.prompt_path.exists()
    assert prepared.prompt_path.read_text(encoding="utf-8")
    assert prepared.log_path.name == "run.log"
    assert "only required interactive input" in prepared.prompt_text
    assert "parallel delegated subprocesses" in prepared.prompt_text
    assert "default to 30 minutes total for the overall autoresearch loop" in prepared.prompt_text


def test_build_worker_command_quotes_prompt_path(tmp_path):
    prompt_path = tmp_path / "prompt file.txt"
    cmd = build_autoresearch_worker_command(
        prompt_path,
        python_executable="/tmp/venv/bin/python",
    )

    assert "/tmp/venv/bin/python" in cmd
    assert "hermes_cli.autoresearch_background" in cmd
    assert "prompt file.txt" in cmd
