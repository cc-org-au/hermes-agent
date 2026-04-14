"""Assemble the effective user prompt for a scheduled cron job (skills + constraints)."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ENVELOPE_SPEC = (
    "[SYSTEM — CRON DELIVERY (mandatory): The user only sees what you put in the JSON block "
    "below. You may reason, use tools, and write drafts before it; that prose is NOT delivered.\n"
    "End your reply with EXACTLY these markers and a single JSON object between them "
    "(optionally wrapped in ```json … ```):\n"
    "###HERMES_CRON_DELIVERY_JSON\n"
    '{ "silent": true }\n'
    "###END_HERMES_CRON_DELIVERY_JSON\n"
    "If there is something to report, use non-empty lines (plain strings, no nested objects):\n"
    "###HERMES_CRON_DELIVERY_JSON\n"
    '{ "silent": false, "lines": ["watchdog-check: ok all_connected=whatsapp,telegram", "sev: 0"] }\n'
    "###END_HERMES_CRON_DELIVERY_JSON\n"
    "When you raise or close an issue that this cron job owns, add an optional follow_up object:\n"
    "###HERMES_CRON_DELIVERY_JSON\n"
    '{ "silent": false, "lines": ["blocker: slack gateway disconnected", "next action: restarting gateway and rechecking"], '
    '"follow_up": { "status": "open", "summary": "Repair slack gateway connectivity for this cron channel", '
    '"requested_action": "Restart the gateway, verify connectivity, and post the resolved status here" } }\n'
    "###END_HERMES_CRON_DELIVERY_JSON\n"
    "Rules: (1) Nothing after ###END_HERMES_CRON_DELIVERY_JSON. "
    "(2) At most 16 lines; each line under ~280 characters; total size respects delivery_max_chars. "
    "(3) Lines must be factual (states, numbers, paths, command output) — no narration, no "
    "“I am sending…”, no web-search essay. "
    "(4) Use {\"silent\": true} when there is no new factual delta since the last run. "
    "(5) Do not use [SILENT], “[Silently …]”, or “I will respond with [SILENT]” — only the JSON block. "
    "(6) If your profile sets cron.strict_delivery_envelope, missing or invalid JSON suppresses "
    "messaging entirely. "
    "(7) When the job surfaces a blocker you can fix with available tools (config, health checks, "
    "documented service restarts), fix it in-run and add JSON lines reporting fixed status; only "
    "escalate what remains impossible to automate safely. "
    "(8) You own any blocker or outstanding task you raise in this channel. If a prior run left an "
    "open follow-up, first try to resolve that before reporting fresh issues. "
    "(9) Use follow_up.status=open for unresolved work you still own, follow_up.status=resolved when "
    "you fixed a previously open item, and follow_up.status=none only when there is truly no owned "
    "follow-up left. "
    "(10) Do not return silent while an owned follow-up remains open or when you resolved one in this "
    "run; send the status update back to this same channel. "
    "(11) Use delegation when a specialist agent would materially help complete the fix.]\n\n"
)


def _pending_follow_up_context(job: dict[str, Any]) -> str:
    follow_up = job.get("pending_follow_up")
    if not isinstance(follow_up, dict):
        return ""
    if str(follow_up.get("status") or "").strip().lower() != "open":
        return ""

    summary = str(follow_up.get("summary") or "").strip() or "(missing summary)"
    requested_action = (
        str(follow_up.get("requested_action") or "").strip() or "(missing requested action)"
    )
    first_raised_at = str(follow_up.get("first_raised_at") or "unknown").strip()
    last_seen_at = str(follow_up.get("last_seen_at") or "unknown").strip()
    deliver = str(job.get("deliver") or "unknown").strip()

    return (
        "[SYSTEM — OWNED FOLLOW-UP (mandatory): A previous run of this same cron job raised an "
        "unresolved issue in this same delivery channel. Your first priority this run is to resolve "
        "or materially advance it before reporting new issues. Do not return silent while it remains "
        "open or when you resolve it.]\n"
        f"- delivery_target: {deliver}\n"
        f"- first_raised_at: {first_raised_at}\n"
        f"- last_seen_at: {last_seen_at}\n"
        f"- summary: {summary}\n"
        f"- requested_action: {requested_action}\n\n"
    )


def build_cron_job_prompt(job: dict[str, Any]) -> str:
    """Build the effective prompt for a cron job, optionally loading one or more skills first."""
    prompt = job.get("prompt", "")
    skills = job.get("skills")

    prompt = _ENVELOPE_SPEC + _pending_follow_up_context(job) + prompt
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
            f"Include that in your JSON lines if the user should know, e.g. "
            f'{{"silent": false, "lines": ["⚠️ Skills skipped: {", ".join(skipped)}"]}}]'
        )
        parts.insert(0, notice)

    if prompt:
        parts.extend(
            ["", f"The user has provided the following instruction alongside the skill invocation: {prompt}"]
        )
    return "\n".join(parts)
