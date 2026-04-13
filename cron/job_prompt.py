"""Assemble the effective user prompt for a scheduled cron job (skills + constraints)."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_cron_job_prompt(job: dict[str, Any]) -> str:
    """Build the effective prompt for a cron job, optionally loading one or more skills first."""
    prompt = job.get("prompt", "")
    skills = job.get("skills")

    silent_hint = (
        "[SYSTEM: If you have a meaningful status report or findings, "
        "send them — that is the whole point of this job. Only respond "
        'with exactly "[SILENT]" (nothing else) when there is genuinely '
        "nothing new to report. [SILENT] suppresses delivery to the user. "
        "Never combine [SILENT] with content — either report your "
        "findings normally, or say [SILENT] and nothing more. Do not write "
        "“I will remain silent”, “the system remains silent”, or "
        "“I will return exactly [SILENT]” — those still notify the user; "
        "use the token [SILENT] alone instead. Do not use bracketed prose like "
        "“[Silently no change]” or “[Silent — no alert]” — only the exact five "
        "characters [SILENT] with nothing else.]\n\n"
        "[SYSTEM — OUTPUT FORMAT (mandatory): Reply with ONLY the factual "
        "information this job is supposed to surface (numbers, states, file "
        "paths, command output, watchdog lines). Do not narrate, explain your "
        "reasoning, describe sending a message, apologize, or say there is "
        "nothing to say — if there is no factual delta, output exactly [SILENT] "
        "alone. Never write meta lines like “I am sending…” or “here is another "
        "message…”. At most four short lines and under 500 characters unless the "
        "job explicitly requires pasting raw logs.]\n\n"
    )
    prompt = silent_hint + prompt
    if skills is None:
        legacy = job.get("skill")
        skills = [legacy] if legacy else []

    skill_names = [str(name).strip() for name in skills if str(name).strip()]
    if not skill_names:
        return prompt

    from tools.skills_tool import skill_view

    parts: list[str] = []
    skipped: list[str] = []
    for skill_name in skill_names:
        loaded = json.loads(skill_view(skill_name))
        if not loaded.get("success"):
            error = loaded.get("error") or f"Failed to load skill '{skill_name}'"
            logger.warning(
                "Cron job '%s': skill not found, skipping — %s",
                job.get("name", job.get("id")),
                error,
            )
            skipped.append(skill_name)
            continue

        content = str(loaded.get("content") or "").strip()
        if parts:
            parts.append("")
        parts.extend(
            [
                f'[SYSTEM: The user has invoked the "{skill_name}" skill, indicating they want you to follow its instructions. The full skill content is loaded below.]',
                "",
                content,
            ]
        )

    if skipped:
        notice = (
            f"[SYSTEM: The following skill(s) were listed for this job but could not be found "
            f"and were skipped: {', '.join(skipped)}. "
            f"Start your response with a brief notice so the user is aware, e.g.: "
            f"'⚠️ Skill(s) not found and skipped: {', '.join(skipped)}']"
        )
        parts.insert(0, notice)

    if prompt:
        parts.extend(
            ["", f"The user has provided the following instruction alongside the skill invocation: {prompt}"]
        )
    return "\n".join(parts)
