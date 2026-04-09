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
    return {
        "enabled": enabled,
        "daily_budget_aud": daily_aud,
        "aud_to_usd": aud_to_usd,
        "daily_cap_usd": daily_aud * aud_to_usd,
        "session_budget_usd": max(0.01, session_usd),
        "spike_threshold_usd_per_min": max(0.01, spike),
        "show_tui_bar": show_tui,
        "reset_timezone": reset_tz,
    }
