"""Workspace token-governance runtime caps (activation Session 6+).

If ``HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml`` exists
and ``enabled: true``, Hermes applies model downgrade rules, iteration caps, optional
``skip_context_files``, and delegation iteration caps on every :class:`~run_agent.AIAgent`
construction.

Model IDs are **not** hardcoded in Hermes: use ``tier_models`` (tiers A–F) and
``tier:D``-style placeholders in ``config.yaml``; see ``agent/tier_model_routing.py``.

Disable entirely with ``HERMES_TOKEN_GOVERNANCE_DISABLE=1``. Allow blocked (premium)
models to pass through with ``HERMES_GOVERNANCE_ALLOW_PREMIUM=1``.
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RUNTIME_FILENAME = "hermes_token_governance.runtime.yaml"
ENV_DISABLE = "HERMES_TOKEN_GOVERNANCE_DISABLE"
ENV_ALLOW_PREMIUM = "HERMES_GOVERNANCE_ALLOW_PREMIUM"


def _operations_dir():
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "workspace" / "operations"


def runtime_config_path() -> str:
    return str(_operations_dir() / RUNTIME_FILENAME)


def load_runtime_config() -> Optional[Dict[str, Any]]:
    if os.environ.get(ENV_DISABLE, "").strip().lower() in ("1", "true", "yes"):
        return None
    path = _operations_dir() / RUNTIME_FILENAME
    if not path.is_file():
        return None
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("token governance runtime: failed to read %s: %s", path, e)
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("enabled", False):
        return None
    return data


def resolve_tier_strings_in_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace ``tier:X`` string values in *config* using runtime ``tier_models``."""
    cfg = load_runtime_config()
    if not cfg:
        return config
    from agent.tier_model_routing import (
        normalize_tier_models,
        resolve_tier_placeholder,
        TIER_SENTINEL_RE,
    )

    tier_models = normalize_tier_models(cfg.get("tier_models"))
    if not tier_models:
        return config

    fb = str(cfg.get("chief_default_tier") or "D").strip().upper()
    if len(fb) != 1 or fb not in "ABCDEF":
        fb = "D"

    out = copy.deepcopy(config)

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if isinstance(v, str) and TIER_SENTINEL_RE.match(v.strip()):
                    obj[k] = resolve_tier_placeholder(v, tier_models, fallback_tier=fb)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(out)
    return out


def apply_token_governance_runtime(agent: Any) -> None:
    """Apply governance caps to a freshly constructed ``AIAgent`` (mutates in place)."""
    cfg = load_runtime_config()
    if not cfg:
        return

    agent._token_governance_cfg = cfg

    from agent.tier_model_routing import (
        normalize_tier_models,
        resolve_tier_placeholder,
        TIER_SENTINEL_RE,
    )

    tier_models = normalize_tier_models(cfg.get("tier_models"))
    chief_tier = str(cfg.get("chief_default_tier") or cfg.get("default_tier") or "D").strip().upper()
    if len(chief_tier) != 1 or chief_tier not in "ABCDEF":
        chief_tier = "D"

    # Resolve tier: sentinel on agent.model before blocklist logic
    if agent.model and TIER_SENTINEL_RE.match(str(agent.model).strip()):
        agent.model = resolve_tier_placeholder(agent.model, tier_models, fallback_tier=chief_tier)

    # Effective "default" for blocklist replacement: explicit default_model, else tier chief_default_tier
    explicit_default = (cfg.get("default_model") or "").strip()
    if explicit_default:
        default_resolved = resolve_tier_placeholder(explicit_default, tier_models, fallback_tier=chief_tier)
    else:
        default_resolved = tier_models.get(chief_tier, "")

    blocked_fb = str(cfg.get("blocked_fallback_tier") or "B").strip().upper()
    if len(blocked_fb) != 1 or blocked_fb not in "ABCDEF":
        blocked_fb = "B"
    blocked_replace = tier_models.get(blocked_fb) or default_resolved

    mlow = (agent.model or "").lower()
    allow_premium = os.environ.get(ENV_ALLOW_PREMIUM, "").strip().lower() in ("1", "true", "yes")

    blocked = cfg.get("blocked_model_substrings") or []
    if isinstance(blocked, str):
        blocked = [blocked]

    if not allow_premium and blocked:
        replacement = blocked_replace if tier_models else default_resolved
        for sub in blocked:
            if sub and str(sub).lower() in mlow:
                new_m = replacement or default_resolved
                if not new_m:
                    break
                logger.warning(
                    "Token governance: model %r matches blocked substring %r; using %r "
                    "(set %s=1 to keep configured model).",
                    agent.model,
                    sub,
                    new_m,
                    ENV_ALLOW_PREMIUM,
                )
                agent.model = new_m
                break

    cap = cfg.get("max_agent_turns")
    if cap is not None:
        try:
            cap_i = int(cap)
            if cap_i > 0 and agent.max_iterations > cap_i:
                logger.info(
                    "Token governance: capping max_iterations %s -> %s",
                    agent.max_iterations,
                    cap_i,
                )
                agent.max_iterations = cap_i
                if getattr(agent, "iteration_budget", None) is not None:
                    agent.iteration_budget.max_total = min(
                        agent.iteration_budget.max_total, cap_i
                    )
        except (TypeError, ValueError):
            pass

    if cfg.get("skip_context_files") is True:
        agent.skip_context_files = True

    dcap = cfg.get("delegation_max_iterations")
    if dcap is not None:
        try:
            agent._token_governance_delegation_max = int(dcap)
        except (TypeError, ValueError):
            agent._token_governance_delegation_max = None
    else:
        agent._token_governance_delegation_max = None

    try:
        is_openrouter = agent._is_openrouter_url()
        is_claude = "claude" in (agent.model or "").lower()
        is_native_anthropic = agent.api_mode == "anthropic_messages"
        agent._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
    except Exception:
        logger.debug("token governance: could not refresh prompt caching flags", exc_info=True)

    # One-line visibility: resolved chief baseline after governance (CLI + gateway lifecycle).
    # Skip for delegated subagents to avoid duplicate lines every child spawn.
    if (
        tier_models
        and (agent.model or "").strip()
        and getattr(agent, "_delegate_depth", 0) == 0
    ):
        try:
            emit = getattr(agent, "_emit_status", None)
            if callable(emit):
                emit(f"Token governance: baseline Tier {chief_tier} → {agent.model}")
            else:
                logger.info("Token governance: baseline Tier %s → %s", chief_tier, agent.model)
        except Exception:
            logger.info("Token governance: baseline Tier %s → %s", chief_tier, agent.model)


def apply_per_turn_tier_model(agent: Any, user_message: str) -> None:
    """Optional per-turn model pick from ``tier_models`` (dynamic tier routing)."""
    from agent.tier_model_routing import (
        normalize_tier_models,
        should_apply_per_turn_routing,
        select_tier_for_message,
    )

    cfg = getattr(agent, "_token_governance_cfg", None) or load_runtime_config()
    if not should_apply_per_turn_routing(cfg):
        return
    tier_models = normalize_tier_models(cfg.get("tier_models"))
    if not tier_models:
        return
    tier = select_tier_for_message(user_message, cfg)
    mid = tier_models.get(tier)
    if not mid:
        return
    changed = mid != agent.model
    if changed:
        logger.info("Token governance: per-turn tier %s -> model %s", tier, mid)
        agent.model = mid
        try:
            is_openrouter = agent._is_openrouter_url()
            is_claude = "claude" in (agent.model or "").lower()
            is_native_anthropic = agent.api_mode == "anthropic_messages"
            agent._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
        except Exception:
            logger.debug("token governance: could not refresh prompt caching flags", exc_info=True)
    # Always show tier + model for this user turn (even if unchanged).
    try:
        emit = getattr(agent, "_emit_status", None)
        if callable(emit):
            emit(f"Token governance: this turn Tier {tier} → {mid}")
        else:
            logger.info("Token governance: this turn Tier %s → %s", tier, mid)
    except Exception:
        logger.info("Token governance: this turn Tier %s → %s", tier, mid)
