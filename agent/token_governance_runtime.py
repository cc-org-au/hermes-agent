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
    from agent.tier_model_routing import (
        effective_tier_models,
        resolve_tier_placeholder,
        TIER_SENTINEL_RE,
        is_tier_dynamic,
    )

    tier_models = effective_tier_models((cfg or {}).get("tier_models"))
    fb = "D"
    if cfg:
        fb = str(cfg.get("chief_default_tier") or "D").strip().upper()
        if len(fb) != 1 or fb not in "ABCDEF":
            fb = "D"

    out = copy.deepcopy(config)

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if (
                    isinstance(v, str)
                    and TIER_SENTINEL_RE.match(v.strip())
                    and not is_tier_dynamic(v)
                ):
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

    from agent.tier_model_routing import (
        effective_tier_models,
        resolve_tier_placeholder,
        TIER_SENTINEL_RE,
        is_tier_dynamic,
        infer_tier_letter_for_model,
    )

    tier_models = effective_tier_models((cfg or {}).get("tier_models"))
    chief_tier = "D"
    if cfg:
        chief_tier = str(cfg.get("chief_default_tier") or cfg.get("default_tier") or "D").strip().upper()
        if len(chief_tier) != 1 or chief_tier not in "ABCDEF":
            chief_tier = "D"

    if not cfg:
        agent._token_governance_cfg = None
        # Still resolve ``tier:X`` so providers never see a literal sentinel when
        # governance YAML is missing or disabled.
        if agent.model and TIER_SENTINEL_RE.match(str(agent.model).strip()):
            agent.model = resolve_tier_placeholder(agent.model, tier_models, fallback_tier=chief_tier)
        try:
            is_openrouter = agent._is_openrouter_url()
            is_claude = "claude" in (agent.model or "").lower()
            is_native_anthropic = agent.api_mode == "anthropic_messages"
            agent._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
        except Exception:
            logger.debug("token governance: could not refresh prompt caching flags", exc_info=True)
        return

    agent._token_governance_cfg = cfg

    # Remember whether the config-supplied model was a tier placeholder.
    # If it was NOT (user set a concrete model like "gpt-5.4"), per-turn
    # tier routing must not override it.
    _raw_model = (agent.model or "").strip()
    _is_tier_placeholder = (
        is_tier_dynamic(_raw_model)
        or bool(TIER_SENTINEL_RE.match(_raw_model))
    )
    agent._model_is_tier_routed = _is_tier_placeholder

    # Resolve tier: sentinel on agent.model before blocklist logic (fixed letter → slug).
    # tier:dynamic is left as-is until apply_per_turn_tier_model (per user message).
    if agent.model and TIER_SENTINEL_RE.match(str(agent.model).strip()):
        agent.model = resolve_tier_placeholder(agent.model, tier_models, fallback_tier=chief_tier)

    # Provisional prompt-caching flags when model is tier:dynamic (probe chief tier slug).
    if agent.model and is_tier_dynamic(agent.model) and tier_models:
        probe = tier_models.get(chief_tier, "")
        if probe:
            _saved = agent.model
            agent.model = probe
            try:
                is_openrouter = agent._is_openrouter_url()
                is_claude = "claude" in (agent.model or "").lower()
                is_native_anthropic = agent.api_mode == "anthropic_messages"
                agent._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
            finally:
                agent.model = _saved

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
            if is_tier_dynamic(agent.model):
                msg = (
                    f"Token governance: baseline tier:dynamic "
                    f"(per-message tier from tier_models; ref chief {chief_tier})"
                )
            else:
                tier_lbl = infer_tier_letter_for_model(agent.model or "", tier_models)
                msg = f"Token governance: baseline Tier {tier_lbl} → {agent.model}"
            emit = getattr(agent, "_emit_status", None)
            if callable(emit):
                emit(msg, "token_governance")
            else:
                logger.info("%s", msg)
        except Exception:
            logger.info("Token governance: baseline → %s", agent.model)


def apply_per_turn_tier_model(agent: Any, user_message: str) -> None:
    """Optional per-turn model pick from ``tier_models`` (dynamic tier routing)."""
    # `/models` pipeline selection: honor user pick for this turn (see run_agent.AIAgent).
    if getattr(agent, "_skip_per_turn_tier_routing", False):
        return
    # Stay on the active provider/model while provider fallback is pinned (e.g. rate limits).
    if getattr(agent, "_fallback_activated", False):
        return
    # If the user set a concrete model in config (not tier:X / tier:dynamic),
    # do not override it with per-turn routing. This ensures /model switches persist.
    if not getattr(agent, "_model_is_tier_routed", True):
        return
    from agent.consultant_routing import (
        consultant_routing_enabled,
        format_status_line,
        is_pushback_message,
        resolve_consultant_tier,
    )
    from agent.tier_model_routing import (
        effective_tier_models,
        should_apply_per_turn_routing,
        select_tier_for_message,
        is_tier_dynamic,
    )

    cfg = getattr(agent, "_token_governance_cfg", None) or load_runtime_config()
    if not cfg:
        return
    tier_models = effective_tier_models(cfg.get("tier_models"))
    cr_on = consultant_routing_enabled(cfg)
    # tier:dynamic, dynamic_tier_routing, or consultant_routing alone can trigger per-turn picks.
    if (
        not is_tier_dynamic(agent.model)
        and not should_apply_per_turn_routing(cfg)
        and not cr_on
    ):
        return
    deterministic_tier = select_tier_for_message(user_message, cfg)
    tier = deterministic_tier
    audit: dict = {}

    # openai_primary_mode: override low-cost deterministic tier with E/F
    _opm = cfg.get("openai_primary_mode") or {}
    if _opm.get("enabled", False) and tier in ("A", "B", "C"):
        _is_coding = any(
            kw in (user_message or "").lower()
            for kw in ("code", "implement", "debug", "refactor", "function",
                       "class", "script", "test", "fix", "bug", "error",
                       "compile", "build", "deploy")
        )
        tier = "F" if _is_coding else "E"
        logger.info(
            "openai_primary_mode: overriding deterministic tier %s → %s",
            deterministic_tier, tier,
        )

    # Detect push-back and repeated-failure signals for escalation.
    pushback = is_pushback_message(user_message)
    retry_count = int(getattr(agent, "_same_task_retry_count", 0) or 0)
    # Track retry count: increment when user pushes back, reset on apparent new task.
    if pushback:
        setattr(agent, "_same_task_retry_count", retry_count + 1)
    elif len((user_message or "").strip()) > 200:
        # Long new message = new task; reset retry counter.
        setattr(agent, "_same_task_retry_count", 0)

    if cr_on:
        try:
            tier, audit = resolve_consultant_tier(
                user_message,
                cfg,
                deterministic_tier,
                tier_models,
                agent=agent,
                pushback_signal=pushback,
                retry_count=retry_count,
            )
        except Exception:
            logger.debug("resolve_consultant_tier failed", exc_info=True)
            tier = deterministic_tier
            audit = {}

    # Enforce OpenAI-primary mode after consultant routing too, so no later
    # router step can drop back to low-cost Gemma tiers when the flag is on.
    if _opm.get("enabled", False) and tier in ("A", "B", "C", "D"):
        _router_rec2 = audit.get("router") if isinstance(audit, dict) else {}
        _coding_hint = bool(
            isinstance(_router_rec2, dict) and _router_rec2.get("coding_task", False)
        )
        _is_coding = _coding_hint or any(
            kw in (user_message or "").lower()
            for kw in (
                "code",
                "implement",
                "debug",
                "refactor",
                "function",
                "class",
                "script",
                "test",
                "fix",
                "bug",
                "error",
                "compile",
                "build",
                "deploy",
            )
        )
        tier = "F" if _is_coding else "E"

    # Store free_model_brief for injection into user message (low-cost tiers A/B/C only).
    _router_rec = audit.get("router") or {}
    _free_brief = _router_rec.get("free_model_brief") if isinstance(_router_rec, dict) else None
    if _free_brief and tier in ("A", "B", "C"):
        setattr(agent, "_free_model_brief_for_turn", str(_free_brief).strip())
    else:
        setattr(agent, "_free_model_brief_for_turn", None)

    # Flag background task detection: signal chief should be consulted before launching.
    _is_bg_task = (
        _router_rec.get("background_task", False) if isinstance(_router_rec, dict) else False
    )
    if _is_bg_task:
        setattr(agent, "_routing_detected_background_task", True)
        logger.info(
            "routing_engine: background task detected — chief orchestrator should be consulted "
            "before launching subprocess; only free local models (gemma-4-31b-it or local inference) permitted "
            "without explicit operator approval"
        )
        emit = getattr(agent, "_emit_status", None)
        if callable(emit):
            emit(
                "⚡ Background task detected — subprocess policy: free models only; "
                "paid models require operator approval",
                "subprocess_governance",
            )
    else:
        setattr(agent, "_routing_detected_background_task", False)

    # Log profile suggestion if routing engine provided one.
    _profile_sug = _router_rec.get("profile_suggestion") if isinstance(_router_rec, dict) else None
    if _profile_sug:
        logger.info("routing_engine: suggested profile=%r for this turn (informational)", _profile_sug)

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
        extra = format_status_line(audit, tier, mid) if audit else ""
        if callable(emit):
            emit(f"Token governance: this turn Tier {tier} → {mid}", "token_governance")
            if extra:
                emit(extra, "consultant")
        else:
            logger.info("Token governance: this turn Tier %s → %s", tier, mid)
            if extra:
                logger.info("%s", extra)
    except Exception:
        logger.info("Token governance: this turn Tier %s → %s", tier, mid)

    # Native OpenAI consultant tiers need api.openai.com + OPENAI_API_KEY; restore baseline otherwise.
    _rebind = getattr(agent, "_reconcile_runtime_after_tier_model_change", None)
    if callable(_rebind):
        try:
            _rebind()
        except Exception:
            logger.debug("tier model runtime reconcile failed", exc_info=True)
