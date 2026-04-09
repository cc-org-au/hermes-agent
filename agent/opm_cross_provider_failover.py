"""OPM quota cascade: native OpenAI ladder → OpenRouter (explicit + auto) → config fallback chain.

Policy lives in merged routing canon (``opm_cross_provider_quota_failover`` + ``opm_native_quota_downgrade``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from utils import is_truthy_value

from agent.opm_quota_ladder import load_opm_native_quota_downgrade_config
from agent.routing_canon import load_merged_routing_canon

logger = logging.getLogger(__name__)


def load_opm_cross_provider_quota_failover_config() -> Dict[str, Any]:
    """Merged canon block with defaults."""
    canon = load_merged_routing_canon()
    raw = canon.get("opm_cross_provider_quota_failover")
    if not isinstance(raw, dict):
        raw = {}
    nat = load_opm_native_quota_downgrade_config()
    enabled = is_truthy_value(raw.get("enabled"), default=True)

    def _norm_list(key: str, derive_from_nat: List[str]) -> List[str]:
        v = raw.get(key)
        if isinstance(v, list) and v:
            return [str(x).strip() for x in v if str(x).strip()]
        return [f"openai/{m}" if not str(m).strip().lower().startswith("openai/") else str(m).strip() for m in derive_from_nat]

    chat_or = _norm_list("openrouter_chat_models", list(nat.get("chat_models") or []))
    codex_or = _norm_list("openrouter_codex_models", list(nat.get("codex_models") or []))

    ora = raw.get("openrouter_auto")
    if not isinstance(ora, dict):
        ora = {}
    auto_on = is_truthy_value(ora.get("enabled"), default=True)
    auto_model = str(ora.get("model") or "openrouter/auto").strip() or "openrouter/auto"

    return {
        "enabled": enabled,
        "openrouter_chat_models": chat_or,
        "openrouter_codex_models": codex_or,
        "openrouter_auto_enabled": auto_on,
        "openrouter_auto_model": auto_model,
    }


def openrouter_api_key_available() -> bool:
    return bool((os.getenv("OPENROUTER_API_KEY") or "").strip())


def openrouter_explicit_models_for_agent(agent: Any, xcfg: Dict[str, Any]) -> List[str]:
    """Ordered OpenRouter hub ids for the current agent stack (chat vs codex)."""
    api_mode = str(getattr(agent, "api_mode", "") or "")
    mid = str(getattr(agent, "model", "") or "").lower()
    if api_mode == "codex_responses" or "codex" in mid:
        return list(xcfg.get("openrouter_codex_models") or [])
    return list(xcfg.get("openrouter_chat_models") or [])


def norm_model_slug(model_id: str) -> str:
    s = str(model_id or "").strip().lower()
    if s.startswith("openai/"):
        s = s[7:]
    return s


def should_run_opm_quota_cascade(
    agent: Any,
    *,
    quota_style: bool,
    pool_may_recover: bool,
) -> bool:
    """Shared eligibility for native + OpenRouter quota steps (not config fallback chain)."""
    if not quota_style or pool_may_recover:
        return False
    try:
        from agent.openai_primary_mode import opm_enabled, opm_manual_override_active

        if not opm_enabled(agent) or opm_manual_override_active(agent):
            return False
    except Exception:
        return False
    if getattr(agent, "_fallback_activated", False):
        return False
    return True
