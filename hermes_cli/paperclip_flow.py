from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from hermes_constants import get_hermes_home
from hermes_cli.integration_repos import resolve_paperclip_repo


class PaperclipFlowError(RuntimeError):
    """Raised when the Paperclip runtime flow cannot proceed."""


@dataclass(frozen=True)
class PaperclipSkillTarget:
    skill_dir_name: str
    user_instruction: str
    mode_label: str


def _expand_path(path: Path) -> str:
    try:
        return str(path).replace(str(Path.home()), "~", 1)
    except Exception:
        return str(path)


def resolve_paperclip_repo_path(config: Optional[Mapping[str, Any]] = None) -> Path:
    configured = resolve_paperclip_repo(config)
    if configured:
        return Path(configured).expanduser()
    return get_hermes_home() / "skills" / "external-repos" / "paperclip"


def resolve_paperclip_skill_path(
    config: Optional[Mapping[str, Any]] = None,
    *,
    skill_dir_name: str = "paperclip",
) -> Path:
    return resolve_paperclip_repo_path(config) / "skills" / skill_dir_name


def _resolve_paperclip_skill_target(user_instruction: str) -> PaperclipSkillTarget:
    cleaned = (user_instruction or "").strip()
    if not cleaned:
        return PaperclipSkillTarget(
            skill_dir_name="paperclip",
            user_instruction="",
            mode_label="coordination session",
        )

    first, _, remainder = cleaned.partition(" ")
    first = first.lower()
    remainder = remainder.strip()
    if first in {"agent", "create-agent", "agents"}:
        return PaperclipSkillTarget(
            skill_dir_name="paperclip-create-agent",
            user_instruction=remainder,
            mode_label="agent workflow",
        )
    if first in {"plugin", "create-plugin", "plugins"}:
        return PaperclipSkillTarget(
            skill_dir_name="paperclip-create-plugin",
            user_instruction=remainder,
            mode_label="plugin workflow",
        )
    return PaperclipSkillTarget(
        skill_dir_name="paperclip",
        user_instruction=cleaned,
        mode_label="coordination session",
    )


def format_paperclip_target_message(config: Optional[Mapping[str, Any]] = None) -> str:
    repo_path = resolve_paperclip_repo_path(config)
    skill_path = resolve_paperclip_skill_path(config)
    return "\n".join(
        [
            f"Paperclip repo: {_expand_path(repo_path)}",
            f"Paperclip skill: {_expand_path(skill_path)}",
            "Run /paperclip to start a Paperclip coordination session for this profile.",
            "Use /paperclip agent <instruction> for agent workflows or /paperclip plugin <instruction> for plugin workflows.",
        ]
    )


def _build_paperclip_runtime_brief(target: PaperclipSkillTarget) -> str:
    cleaned = (target.user_instruction or "").strip()
    lines = [
        f"Start a Paperclip {target.mode_label} now.",
        f"Use the installed Paperclip `{target.skill_dir_name}` skill from the configured Paperclip repo for this Hermes profile.",
        "If the Paperclip runtime environment is already present, follow the skill's heartbeat or manual-session workflow directly.",
        "If the Paperclip runtime environment is not present, use the repo-local CLI from the Paperclip repo root instead of giving generic setup docs.",
        "When Paperclip CLI commands are needed, run them from the Paperclip repo root and prefer `pnpm paperclipai ...` forms.",
        "Keep replies concise and focused on the active Paperclip task.",
    ]
    if cleaned:
        lines.insert(1, f"User request for this Paperclip session: {cleaned}")
    else:
        lines.append(
            "If no specific Paperclip task was provided, inspect the current Paperclip context first and continue with the most relevant next action."
        )
    return "\n".join(lines)


def _build_paperclip_runtime_note(repo_path: Path, skill_path: Path) -> str:
    return " ".join(
        [
            f"The Paperclip repo for this Hermes profile is `{_expand_path(repo_path)}`.",
            f"The bundled Paperclip skill is at `{_expand_path(skill_path)}`.",
            "When a Paperclip CLI command is needed, run it from the repo root.",
            "If you need to start or repair the local Paperclip instance, prefer `pnpm paperclipai run` or `pnpm paperclipai doctor` from that repo.",
        ]
    )


def build_paperclip_skill_message(
    *,
    user_instruction: str = "",
    task_id: str | None = None,
    config: Optional[Mapping[str, Any]] = None,
) -> str:
    from agent.skill_commands import build_explicit_skill_invocation_message

    repo_path = resolve_paperclip_repo_path(config)
    target = _resolve_paperclip_skill_target(user_instruction)
    skill_path = resolve_paperclip_skill_path(
        config,
        skill_dir_name=target.skill_dir_name,
    )

    if not repo_path.exists():
        raise PaperclipFlowError(
            f"Paperclip repo not found at `{_expand_path(repo_path)}`."
        )
    if not (skill_path / "SKILL.md").exists():
        raise PaperclipFlowError(
            f"Paperclip skill not found at `{_expand_path(skill_path)}`."
        )

    msg = build_explicit_skill_invocation_message(
        str(skill_path),
        _build_paperclip_runtime_brief(target),
        task_id=task_id,
        runtime_note=_build_paperclip_runtime_note(repo_path, skill_path),
    )
    if not msg:
        raise PaperclipFlowError(
            "Failed to load the installed Paperclip skill for this profile."
        )
    return msg
