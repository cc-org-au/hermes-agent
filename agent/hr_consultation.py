"""Optional automatic HR / org consultation before the chief model acts.

Configured under ``hr_consultation`` in
``HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml`` (same file as
token governance). When enabled and triggers match the user message, Hermes runs
``delegate_task`` against the named Hermes profile (default ``ag-org-hr``) and
appends the subagent summary to this turn's user message so the chief genuinely
incorporates HR input in the same turn.

Skipped for subagents (delegation depth > 0) and when the parent lacks ``delegate_task``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _hr_cfg(gov: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not gov or not isinstance(gov, dict):
        return {}
    raw = gov.get("hr_consultation")
    return raw if isinstance(raw, dict) else {}


def hr_consultation_triggers(user_message: str, cfg: Dict[str, Any]) -> bool:
    """Return True when *user_message* should invoke HR profile consultation."""
    if not cfg.get("enabled", False):
        return False
    text = (user_message or "").strip()
    if not text:
        return False
    min_len = cfg.get("min_message_chars")
    if min_len is not None:
        try:
            if len(text) < int(min_len):
                return False
        except (TypeError, ValueError):
            pass
    kws = cfg.get("trigger_keywords") or []
    if isinstance(kws, str):
        kws = [kws]
    if not isinstance(kws, list) or not kws:
        return False
    low = text.lower()
    for k in kws:
        if not k:
            continue
        if str(k).lower() in low:
            return True
    return False


def _parent_can_delegate(agent: Any) -> bool:
    depth = getattr(agent, "_delegate_depth", 0) or 0
    if depth > 0:
        return False
    names = getattr(agent, "valid_tool_names", None) or []
    if isinstance(names, (list, tuple, set, frozenset)):
        return "delegate_task" in names
    return False


def maybe_append_hr_consultation(agent: Any, user_message: str, gov: Optional[Dict[str, Any]]) -> str:
    """If configured and triggered, run HR subagent and append summary to *user_message*."""
    cfg = _hr_cfg(gov)
    if not hr_consultation_triggers(user_message, cfg):
        return user_message
    if not _parent_can_delegate(agent):
        logger.debug("hr_consultation: skip (subagent or no delegate_task)")
        return user_message

    profile = str(cfg.get("hermes_profile") or "ag-org-hr").strip() or "ag-org-hr"
    goal = str(
        cfg.get("goal")
        or (
            "From an org / HR controller perspective, review the operator message in context. "
            "State: (1) alignment with ORG_REGISTRY / escalation playbooks, (2) any missing "
            "approvals, (3) recommended next step for the chief. Be concise and actionable."
        )
    ).strip()
    max_iter = cfg.get("max_iterations", 28)
    try:
        max_i = int(max_iter) if max_iter is not None else 28
    except (TypeError, ValueError):
        max_i = 28

    try:
        from tools.delegate_tool import delegate_task

        raw = delegate_task(
            goal=goal,
            context=user_message[:24000],
            hermes_profile=profile,
            max_iterations=max_i,
            parent_agent=agent,
        )
        data = json.loads(raw) if raw else {}
        if isinstance(data, dict) and data.get("error"):
            logger.warning("hr_consultation: delegate_task error: %s", data.get("error"))
            return user_message
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return user_message
        summary = (results[0].get("summary") or "").strip()
        if not summary:
            return user_message
    except Exception as e:
        logger.warning("hr_consultation: failed: %s", e)
        return user_message

    banner = str(cfg.get("injection_banner") or "HR / org consultation (delegated profile)").strip()
    try:
        emit = getattr(agent, "_emit_status", None)
        if callable(emit):
            emit(f"Consulted {profile}: appended summary to this turn.")
    except Exception:
        pass

    return (
        f"{user_message}\n\n---\n[{banner} — profile `{profile}`]\n{summary}\n---\n"
    )
