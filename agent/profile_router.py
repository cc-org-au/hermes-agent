"""Optional LLM-based routing of user prompts to named Hermes profiles (CLI).

When ``agent.profile_router.enabled`` is true, the CLI may delegate a user turn
to another profile via ``delegate_task(hermes_profile=...)`` *before* the main
``run_conversation`` loop, so the specialist profile's config/toolsets apply.

This is **off by default** (extra latency + cost; chief/orchestrator stays in control).
Does not mutate sticky ``active_profile`` — only per-turn delegation.

Automatic profile creation, ORG_REGISTRY edits, and destructive lifecycle actions
are **out of scope** here; use ``hermes profile lifecycle-audit`` (dry-run) and
operator-approved workflows per policy docs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _profiles_root() -> Path:
    return Path.home() / ".hermes" / "profiles"


def list_routable_profile_names() -> List[str]:
    """Return sorted directory names under ~/.hermes/profiles (kebab-case slugs)."""
    root = _profiles_root()
    if not root.is_dir():
        return []
    names = [
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    return sorted(names)


def _parse_router_json(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None
    raw = text.strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def classify_profile_for_prompt(
    user_message: str,
    *,
    candidates: List[str],
    current_profile: str,
    router_cfg: Dict[str, Any],
) -> Tuple[Optional[str], float, str]:
    """Call auxiliary LLM; return (target_profile or None, confidence, reason)."""
    if not candidates:
        return None, 0.0, "no profiles"
    threshold = float(router_cfg.get("confidence_threshold") or 0.72)
    min_chars = int(router_cfg.get("min_message_chars") or 12)
    if len((user_message or "").strip()) < min_chars:
        return None, 0.0, "message too short"

    exclude = set(router_cfg.get("exclude_profiles") or [])
    allow_only = router_cfg.get("allow_only_profiles") or []
    if allow_only:
        candidates = [c for c in candidates if c in allow_only]
    candidates = [c for c in candidates if c not in exclude]
    if not candidates:
        return None, 0.0, "no candidates after filters"

    only_from = router_cfg.get("only_when_current_profiles") or []
    if only_from and current_profile not in only_from:
        return None, 0.0, "current profile not in only_when_current_profiles"

    skip_current = router_cfg.get("exclude_current_profile", True)
    if skip_current and current_profile in candidates and current_profile != "default":
        # Still allow routing *to* another profile when current is chief; remove self from targets only if same name chosen later
        pass

    model_override = (router_cfg.get("router_model") or "").strip() or None
    provider_override = (router_cfg.get("router_provider") or "").strip() or None

    system = (
        "You route user messages to Hermes profile slugs. Reply with ONLY valid JSON, no markdown.\n"
        'Schema: {"profile": "<exact slug from list or null>", "confidence": number 0-1, "reason": "brief"}\n'
        "Choose a profile only when the message clearly needs that specialist's isolated runtime.\n"
        "If unsure, use profile null with low confidence.\n"
        "Never invent slugs; profile must be one of the listed names or null."
    )
    user = (
        f"Current session profile: {current_profile!r}\n"
        f"Available profile slugs: {', '.join(candidates)}\n\n"
        f"User message:\n{user_message.strip()[:8000]}"
    )

    try:
        from agent.auxiliary_client import call_llm, extract_content_or_reasoning

        resp = call_llm(
            task="profile_router",
            provider=provider_override,
            model=model_override,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=256,
        )
        text = extract_content_or_reasoning(resp)
    except Exception as exc:
        logger.warning("profile_router LLM call failed: %s", exc)
        return None, 0.0, f"router error: {exc}"

    data = _parse_router_json(text)
    if not data:
        logger.debug("profile_router: unparseable response: %s", text[:200])
        return None, 0.0, "unparseable router output"

    name = data.get("profile")
    if name is not None and not isinstance(name, str):
        name = None
    if name is not None:
        name = name.strip()
        if name == "" or name.lower() == "null":
            name = None

    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(data.get("reason") or "").strip()[:500]

    if name is None or conf < threshold:
        return None, conf, reason or "below threshold"

    if name not in candidates:
        logger.info("profile_router: model chose unknown profile %r", name)
        return None, conf, "unknown profile slug"

    if skip_current and name == current_profile:
        return None, conf, "target is current profile"

    return name, conf, reason


def route_and_delegate_if_configured(
    *,
    user_message: str,
    parent_agent: Any,
    agent_config: Dict[str, Any],
    current_profile: str,
) -> Optional[str]:
    """If routing applies, run delegate_task and return markdown for the user; else None."""
    router_cfg = agent_config if isinstance(agent_config, dict) else {}
    if not router_cfg.get("enabled"):
        return None

    candidates = list_routable_profile_names()
    target, conf, reason = classify_profile_for_prompt(
        user_message,
        candidates=candidates,
        current_profile=current_profile,
        router_cfg=router_cfg,
    )
    if not target:
        return None

    from tools.delegate_tool import delegate_task

    payload = delegate_task(
        goal=user_message.strip(),
        context=(
            f"Routed automatically from profile {current_profile!r} "
            f"(router confidence {conf:.2f}). Reason: {reason}"
        ),
        hermes_profile=target,
        parent_agent=parent_agent,
    )
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("error"):
        logger.warning("profile_router delegate failed: %s", data.get("error"))
        return None

    # Format a concise reply for the CLI (delegate returns JSON with results[])
    results = data.get("results")
    body = payload
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            body = first.get("summary") or first.get("response") or json.dumps(first, indent=2)[:12000]
    header = f"_Delegated to profile `{target}` (router confidence {conf:.2f})_\n\n"
    return header + (body if isinstance(body, str) else str(body))
