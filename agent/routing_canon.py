"""Layered routing canon: repo defaults + ``${HERMES_HOME}/routing_canon.yaml``.

Single entrypoint for merged policy used by consultant routing, token governance,
and tracing. See ``AGENTS.md`` (Routing canon).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REPO_DEFAULT = Path(__file__).resolve().parent / "dynamic_routing_canon.yaml"
_HOME_REL = "routing_canon.yaml"

_merged_cache: Optional[Dict[str, Any]] = None
_merged_cache_home: Optional[str] = None


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("routing_canon: failed to read %s: %s", path, e)
        return {}


def load_merged_routing_canon(*, force_reload: bool = False) -> Dict[str, Any]:
    """Load repo default merged with ``get_hermes_home() / routing_canon.yaml``."""
    global _merged_cache, _merged_cache_home
    from hermes_constants import get_hermes_home

    home = str(get_hermes_home())
    if not force_reload and _merged_cache is not None and _merged_cache_home == home:
        return _merged_cache

    base = _load_yaml(_REPO_DEFAULT)
    overlay_path = get_hermes_home() / _HOME_REL
    overlay = _load_yaml(overlay_path)
    merged = _deep_merge(base, overlay) if overlay else copy.deepcopy(base)
    _merged_cache = merged
    _merged_cache_home = home
    return merged


def invalidate_routing_canon_cache() -> None:
    global _merged_cache, _merged_cache_home
    _merged_cache = None
    _merged_cache_home = None


def merge_canon_into_consultant_routing(cr: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay ``consultant_escalation`` + ``openrouter_auto`` from merged canon onto *cr*."""
    canon = load_merged_routing_canon()
    ce = canon.get("consultant_escalation")
    if isinstance(ce, dict):
        cr = _deep_merge(cr, ce)
    ora = canon.get("openrouter_auto")
    if isinstance(ora, dict):
        # Stored for resolve_consultant_tier; merge explicit keys only
        if "deliberation_tiers" in ora:
            dt = ora["deliberation_tiers"]
            if isinstance(dt, list):
                cr["openrouter_auto_deliberation_tiers"] = [str(x).strip().upper() for x in dt if x]
        if "openrouter_tier_g_always_deliberate" in ora:
            cr["openrouter_tier_g_always_deliberate"] = bool(ora["openrouter_tier_g_always_deliberate"])
    return cr


def operator_gate_config() -> Dict[str, Any]:
    canon = load_merged_routing_canon()
    og = canon.get("operator_gate")
    return og if isinstance(og, dict) else {}


def openrouter_auto_deliberation_tiers(cr: Dict[str, Any]) -> set:
    raw = cr.get("openrouter_auto_deliberation_tiers")
    if isinstance(raw, list) and raw:
        return {str(x).strip().upper() for x in raw if x}
    return {"D", "E", "F", "G"}


@dataclass(frozen=True)
class TurnRoutingIntent:
    """Per-turn routing snapshot (after tier application)."""

    canon_version: int
    manual_pipeline: bool
    opm_suppressed_for_turn: bool
    opm_coercion_effective: bool
    fallback_activated: bool


def build_turn_routing_intent(agent: Any) -> TurnRoutingIntent:
    from agent.openai_primary_mode import opm_coercion_effective

    canon = load_merged_routing_canon()
    try:
        ver = int(canon.get("version") or 1)
    except (TypeError, ValueError):
        ver = 1
    # Manual /models persists via _defer_opm_primary_coercion (skip flag is cleared
    # after apply_per_turn_tier_model in run_conversation).
    manual = bool(getattr(agent, "_defer_opm_primary_coercion", False))
    return TurnRoutingIntent(
        canon_version=ver,
        manual_pipeline=manual,
        opm_suppressed_for_turn=bool(getattr(agent, "_opm_suppressed_for_turn", False)),
        opm_coercion_effective=bool(opm_coercion_effective(agent)),
        fallback_activated=bool(getattr(agent, "_fallback_activated", False)),
    )


def load_hard_budget_config() -> Dict[str, Any]:
    """Hard budget / cost bar settings from merged routing canon."""
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    hb = canon.get("hard_budget")
    if not isinstance(hb, dict):
        hb = {}
    enabled = is_truthy_value(hb.get("enabled"), default=True)
    try:
        daily_aud = float(hb.get("daily_budget_aud") if hb.get("daily_budget_aud") is not None else 10.0)
    except (TypeError, ValueError):
        daily_aud = 10.0
    try:
        aud_to_usd = float(hb.get("aud_to_usd") if hb.get("aud_to_usd") is not None else 0.65)
    except (TypeError, ValueError):
        aud_to_usd = 0.65
    try:
        session_usd = float(hb.get("session_budget_usd") if hb.get("session_budget_usd") is not None else 2.5)
    except (TypeError, ValueError):
        session_usd = 2.5
    try:
        spike = float(
            hb.get("spike_threshold_usd_per_min")
            if hb.get("spike_threshold_usd_per_min") is not None
            else 0.5
        )
    except (TypeError, ValueError):
        spike = 0.5
    show_tui = is_truthy_value(hb.get("show_tui_bar"), default=True)
    daily_aud = max(0.01, daily_aud)
    aud_to_usd = max(1e-9, aud_to_usd)
    reset_tz = str(
        hb.get("reset_timezone")
        or hb.get("daily_reset_timezone")
        or "Australia/Sydney"
    ).strip() or "Australia/Sydney"
    operator_approval = is_truthy_value(
        hb.get("operator_approval_when_daily_cap_exceeded"),
        default=False,
    )
    return {
        "enabled": enabled,
        "daily_budget_aud": daily_aud,
        "aud_to_usd": aud_to_usd,
        "daily_cap_usd": daily_aud * aud_to_usd,
        "session_budget_usd": max(0.01, session_usd),
        "spike_threshold_usd_per_min": max(0.01, spike),
        "show_tui_bar": show_tui,
        "reset_timezone": reset_tz,
        "operator_approval_when_daily_cap_exceeded": operator_approval,
    }


def load_compression_canon_config() -> Dict[str, Any]:
    """Compression defaults from merged routing canon (canon-first merge in run_agent)."""
    canon = load_merged_routing_canon()
    raw = canon.get("compression")
    if not isinstance(raw, dict):
        raw = {}
    try:
        turn_interval = int(raw.get("turn_interval") or 0)
    except (TypeError, ValueError):
        turn_interval = 0
    try:
        preserve_last = int(raw.get("preserve_last_pairs") or 2)
    except (TypeError, ValueError):
        preserve_last = 2
    return {
        "turn_interval": max(0, turn_interval),
        "lossy_mode": bool(raw.get("lossy_mode", False)),
        "preserve_last_pairs": max(1, preserve_last),
    }


def load_openrouter_free_router_config() -> Dict[str, Any]:
    """openrouter/free synthetic selector policy from merged canon."""
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    raw = canon.get("openrouter_free_router")
    if not isinstance(raw, dict):
        raw = {}
    candidates = raw.get("candidate_slugs")
    if not isinstance(candidates, list):
        candidates = []
    slugs = [str(x).strip() for x in candidates if x and str(x).strip()]
    scores_raw = raw.get("capability_scores")
    scores: Dict[str, int] = {}
    if isinstance(scores_raw, dict):
        for k, v in scores_raw.items():
            key = str(k).strip()
            if not key:
                continue
            try:
                scores[key] = int(v)
            except (TypeError, ValueError):
                continue
    try:
        ttl = int(raw.get("live_fetch_ttl_seconds") or 3600)
    except (TypeError, ValueError):
        ttl = 3600
    return {
        "enabled": is_truthy_value(raw.get("enabled"), default=True),
        "strict_no_paid_fallback": is_truthy_value(raw.get("strict_no_paid_fallback"), default=True),
        "ranking": str(raw.get("ranking") or "capability_score").strip() or "capability_score",
        "live_fetch_ttl_seconds": max(60, ttl),
        "empty_error_message": str(raw.get("empty_error_message") or "").strip()
        or "openrouter/free: no eligible free-tier models.",
        "candidate_slugs": slugs,
        "capability_scores": scores,
    }


def load_lazy_tool_loading_config() -> Dict[str, Any]:
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    raw = canon.get("agent_lazy_tool_loading")
    if not isinstance(raw, dict):
        raw = {}
    core_ts = raw.get("core_toolsets")
    if not isinstance(core_ts, list):
        core_ts = ["memory"]
    core_tools = raw.get("core_tools")
    if not isinstance(core_tools, list):
        core_tools = []
    return {
        "enabled": is_truthy_value(raw.get("enabled"), default=False),
        "core_toolsets": [str(x).strip() for x in core_ts if str(x).strip()],
        "core_tools": [str(x).strip() for x in core_tools if str(x).strip()],
        "expand_via": str(raw.get("expand_via") or "meta_tool").strip() or "meta_tool",
    }


def load_semantic_cache_config() -> Dict[str, Any]:
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    raw = canon.get("agent_semantic_cache")
    if not isinstance(raw, dict):
        raw = {}
    allow = raw.get("allow_tools")
    if not isinstance(allow, list):
        allow = []
    prec = raw.get("host_role_env_precedence")
    if not isinstance(prec, list):
        prec = ["HERMES_CLI_INSTANCE_LABEL", "HERMES_GATEWAY_LOCK_INSTANCE"]
    try:
        ttl = int(raw.get("ttl_seconds") or 3600)
    except (TypeError, ValueError):
        ttl = 3600
    return {
        "enabled": is_truthy_value(raw.get("enabled"), default=False),
        "ttl_seconds": max(60, ttl),
        "sqlite_relpath": str(raw.get("sqlite_relpath") or "semantic_tool_cache.sqlite").strip()
        or "semantic_tool_cache.sqlite",
        "allow_tools": [str(x).strip() for x in allow if str(x).strip()],
        "host_role_env_precedence": [str(x).strip() for x in prec if str(x).strip()],
    }


def load_cost_caps_config() -> Dict[str, Any]:
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    raw = canon.get("agent_cost_caps")
    if not isinstance(raw, dict):
        raw = {}
    kws = raw.get("extractive_keywords")
    if not isinstance(kws, list):
        kws = []
    tiers = raw.get("preserve_full_for_tiers")
    if not isinstance(tiers, list):
        tiers = ["E", "F", "G"]
    try:
        max_out = int(raw.get("extractive_max_output_tokens") or 1024)
    except (TypeError, ValueError):
        max_out = 1024
    try:
        max_um = int(raw.get("extractive_user_message_max_chars") or 800)
    except (TypeError, ValueError):
        max_um = 800
    return {
        "enabled": is_truthy_value(raw.get("enabled"), default=False),
        "extractive_max_output_tokens": max(256, max_out),
        "extractive_user_message_max_chars": max(100, max_um),
        "extractive_keywords": [str(x).strip().lower() for x in kws if str(x).strip()],
        "preserve_full_for_tiers": [str(x).strip().upper() for x in tiers if x],
    }


def load_concise_output_config() -> Dict[str, Any]:
    from utils import is_truthy_value

    canon = load_merged_routing_canon()
    raw = canon.get("agent_concise_output")
    if not isinstance(raw, dict):
        raw = {}
    frag = raw.get("ephemeral_fragment")
    return {
        "enabled": is_truthy_value(raw.get("enabled"), default=False),
        "ephemeral_fragment": str(frag).strip() if frag else "",
    }
