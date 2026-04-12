"""OpenRouter step-up routing: start at the cheapest hub id, escalate toward the tier ceiling.

Escalation triggers (routing_canon ``openrouter_step_up_escalation``):
  - Quota / rate-limit class API errors on the current rung (before OPM cross-provider cascade).
  - Optional: assistant replies with the escalate marker only (see system suffix).

This is the inverse direction of ``opm_native_quota_downgrade`` (expensive→cheap on quota).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from utils import is_truthy_value

from agent.routing_canon import load_merged_routing_canon

logger = logging.getLogger(__name__)

_DEFAULT_MARKER = "[HERMES_ESCALATE]"


def load_openrouter_step_up_config() -> Dict[str, Any]:
    """Merged ``openrouter_step_up_escalation`` block with defaults."""
    canon = load_merged_routing_canon()
    raw = canon.get("openrouter_step_up_escalation")
    if not isinstance(raw, dict):
        raw = {}
    enabled = is_truthy_value(raw.get("enabled"), default=True)
    chat = [str(x).strip() for x in (raw.get("chat_models") or []) if str(x).strip()]
    codex = [str(x).strip() for x in (raw.get("codex_models") or []) if str(x).strip()]
    if not chat:
        chat = [
            "openai/gpt-5-nano",
            "openai/gpt-4.1-nano",
            "openai/gpt-5-mini",
            "openai/gpt-4.1-mini",
            "openai/gpt-5.4-nano",
            "openai/gpt-5.4-mini",
            "openai/gpt-5.2",
            "openai/gpt-5.4",
        ]
    if not codex:
        codex = [
            "openai/gpt-5.2-codex",
            "openai/gpt-5.3-codex",
        ]
    max_esc = int(raw.get("max_escalations_per_turn") or 12)
    return {
        "enabled": enabled,
        "chat_models": chat,
        "codex_models": codex,
        "max_escalations_per_turn": max(1, max_esc),
        "escalate_on_quota_errors": is_truthy_value(
            raw.get("escalate_on_quota_errors"), default=True,
        ),
        "escalate_on_escalate_marker": is_truthy_value(
            raw.get("escalate_on_escalate_marker"), default=True,
        ),
        "escalate_marker": str(raw.get("escalate_marker") or _DEFAULT_MARKER).strip()
        or _DEFAULT_MARKER,
    }


def _norm_slug(model_id: str) -> str:
    from agent.opm_cross_provider_failover import norm_model_slug

    return norm_model_slug(model_id)


def build_ladder_to_ceiling(ordered_cheap_to_capable: List[str], ceiling: str) -> List[str]:
    """Return a prefix of *ordered_cheap_to_capable* up through *ceiling*, else append *ceiling*."""
    c = _norm_slug(ceiling)
    out: List[str] = []
    for m in ordered_cheap_to_capable:
        out.append(m)
        if _norm_slug(m) == c:
            return out
    ce = (ceiling or "").strip()
    if ce and _norm_slug(ce) not in {_norm_slug(x) for x in out}:
        out.append(ce)
    return out


def _hub_models_for_agent(agent: Any, cfg: Dict[str, Any]) -> List[str]:
    """Match :func:`openrouter_explicit_models_for_agent` — slug-driven, not ``api_mode``."""
    mid = str(getattr(agent, "model", "") or "")
    bare = _norm_slug(mid)
    low = mid.lower()
    if "codex" in bare.lower() or "codex" in low:
        return list(cfg.get("codex_models") or [])
    return list(cfg.get("chat_models") or [])


def _non_openai_hub_ceiling(ceiling: str) -> bool:
    low = (ceiling or "").strip().lower()
    if not low:
        return True
    if low.startswith("google/") or "gemini" in low:
        return True
    if low.startswith("openrouter/") and "openai/" not in low:
        return True
    return False


def apply_cross_provider_openrouter_first_hop(
    agent: Any,
    explicit_models_top_first: List[str],
) -> Optional[str]:
    """Pick cheapest hub id toward *explicit_models_top_first[0]*; init ``_or_stepup_*`` on *agent*.

    Used when OPM hops from native OpenAI (or unknown OR slug) onto OpenRouter so the first
    attempt matches step-up (nano→…) instead of the failover list's flagship-first entry.

    Returns the hub id to pass to ``_apply_opm_openrouter_quota_runtime``, or ``None`` to
    fall back to *explicit_models_top_first[0]*.
    """
    cfg = load_openrouter_step_up_config()
    if not cfg.get("enabled"):
        return None
    if not explicit_models_top_first:
        return None
    ceiling = str(explicit_models_top_first[0]).strip()
    if not ceiling or _non_openai_hub_ceiling(ceiling):
        return None
    ordered = _hub_models_for_agent(agent, cfg)
    ladder = build_ladder_to_ceiling(ordered, ceiling)
    if len(ladder) < 2:
        return None
    agent._or_stepup_ladder = ladder
    agent._or_stepup_idx = 0
    agent._or_stepup_ceiling = ceiling
    agent._or_stepup_escalations = 0
    agent._or_stepup_max_escalations = int(cfg.get("max_escalations_per_turn") or 12)
    agent._or_stepup_escalate_on_quota = bool(cfg.get("escalate_on_quota_errors"))
    agent._or_stepup_escalate_on_marker = bool(cfg.get("escalate_on_escalate_marker"))
    agent._or_stepup_marker = str(cfg.get("escalate_marker") or _DEFAULT_MARKER)
    return ladder[0]


def compute_openrouter_step_up_plan(agent: Any) -> Optional[Dict[str, Any]]:
    """Return step-up plan dict or None when step-up should not run this turn."""
    cfg = load_openrouter_step_up_config()
    if not cfg.get("enabled"):
        return None
    if getattr(agent, "_defer_opm_primary_coercion", False):
        return None
    if getattr(agent, "_skip_per_turn_tier_routing", False):
        return None
    if not bool(getattr(agent, "_model_is_tier_routed", True)):
        return None
    try:
        if not agent._is_openrouter_url():
            return None
    except Exception:
        return None
    if getattr(agent, "_fallback_activated", False):
        return None

    ceiling = str(getattr(agent, "model", None) or "").strip()
    if not ceiling or _non_openai_hub_ceiling(ceiling):
        return None

    ordered = _hub_models_for_agent(agent, cfg)
    ladder = build_ladder_to_ceiling(ordered, ceiling)
    if len(ladder) < 2:
        return None

    marker = str(cfg.get("escalate_marker") or _DEFAULT_MARKER)
    suffix = ""
    if cfg.get("escalate_on_escalate_marker"):
        suffix = (
            "\n\n[OpenRouter step-up routing] If this request is beyond what you can do "
            f"reliably on this model, respond with a single line containing exactly `{marker}` "
            "and nothing else. Otherwise answer normally."
        )

    return {
        "ladder": ladder,
        "ceiling": ceiling,
        "start_model": ladder[0],
        "system_suffix": suffix,
        "marker": marker,
        "max_escalations": int(cfg.get("max_escalations_per_turn") or 12),
        "escalate_on_quota_errors": bool(cfg.get("escalate_on_quota_errors")),
        "escalate_on_escalate_marker": bool(cfg.get("escalate_on_escalate_marker")),
    }


def content_requests_escalation(raw_text: str, marker: str) -> bool:
    """True when stripped assistant text is only the marker (optional surrounding whitespace)."""
    t = (raw_text or "").strip()
    if not t:
        return False
    m = (marker or _DEFAULT_MARKER).strip()
    # Strip common think wrappers — caller may pre-strip
    if t == m:
        return True
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    return len(lines) == 1 and lines[0] == m


def strip_escalation_marker_line(text: str, marker: str) -> str:
    """Remove a lone marker line from text (best-effort)."""
    if not text:
        return text
    m = re.escape((marker or _DEFAULT_MARKER).strip())
    return re.sub(rf"(?m)^\s*{m}\s*$", "", text).strip()
