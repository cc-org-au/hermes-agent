"""Workspace token-governance runtime caps (activation Session 6+).

If ``HERMES_HOME/workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml`` exists
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

from agent.disallowed_model_family import model_id_contains_disallowed_family
from agent.openai_primary_mode import (
    opm_auxiliary_model,
    opm_effective_for_tier_routing_uplift,
    opm_enabled,
    opm_manual_override_active,
    resolve_openai_primary_mode,
)
from agent.routing_trace import emit_routing_decision_trace
from agent.trivial_prompt import trivial_message_skips_opm_tier_uplift

logger = logging.getLogger(__name__)

RUNTIME_FILENAME = "hermes_token_governance.runtime.yaml"
ENV_DISABLE = "HERMES_TOKEN_GOVERNANCE_DISABLE"
ENV_ALLOW_PREMIUM = "HERMES_GOVERNANCE_ALLOW_PREMIUM"


def _operations_dir():
    from hermes_constants import get_workspace_operations_dir

    return get_workspace_operations_dir()


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
    # With OpenAI-primary mode + native OpenAI, keep per-turn routing active even if
    # model.default is currently a concrete slug (legacy/stale profile config).
    # Manual ``/models`` routes set ``_defer_opm_primary_coercion`` — treat as explicit
    # concrete model so OPM does not force tier placeholders or blocklist swaps.
    _, _opm_meta = resolve_openai_primary_mode(agent)
    if opm_effective_for_tier_routing_uplift(agent):
        _is_tier_placeholder = True
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

    if not allow_premium and blocked and not getattr(agent, "_defer_opm_primary_coercion", False):
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

    emit_routing_decision_trace(
        stage="token_governance_baseline",
        chosen_model=str(agent.model or ""),
        chosen_provider=str(getattr(agent, "provider", "") or ""),
        reason_code="baseline_apply_runtime",
        opm_enabled=bool(_opm_meta.get("enabled", False)),
        opm_source=str(_opm_meta.get("source", "")),
        tier_source="chief_default",
        skip_flags={},
        fallback_activated=bool(getattr(agent, "_fallback_activated", False)),
        explicit_user_model=not bool(agent._model_is_tier_routed),
        profile=str(getattr(agent, "profile", "") or ""),
        session_id=str(getattr(agent, "session_id", "") or ""),
    )


def inherit_token_governance_from_parent(child: Any, parent: Any) -> None:
    """Copy parent's loaded runtime governance onto the child when the child missed it.

    ``AIAgent.__init__`` calls ``apply_token_governance_runtime``, which no-ops when
    ``load_runtime_config()`` is empty. That happens for delegated children when
    ``HERMES_HOME`` points at a profile without
    ``workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml`` (notably
    ``delegate_task(..., hermes_profile=…)``). The parent chief often still has a
    cached ``_token_governance_cfg`` from its own home. Without inheriting it,
    ``apply_per_turn_tier_model`` exits immediately and the child can remain on a
    free Gemini tier despite OpenAI-primary mode on the parent.
    """
    if getattr(child, "_token_governance_cfg", None) is not None:
        return
    pc = getattr(parent, "_token_governance_cfg", None) or load_runtime_config()
    if not pc:
        return
    child._token_governance_cfg = pc
    from agent.tier_model_routing import TIER_SENTINEL_RE, is_tier_dynamic

    _raw = (getattr(child, "model", None) or "").strip()
    _is_tier_placeholder = is_tier_dynamic(_raw) or bool(TIER_SENTINEL_RE.match(_raw))
    _, _opm_meta = resolve_openai_primary_mode(child)
    if opm_enabled(child) and not getattr(child, "_defer_opm_primary_coercion", False):
        _is_tier_placeholder = True
    child._model_is_tier_routed = _is_tier_placeholder
    child._last_opm_meta = _opm_meta


def _opm_clamp_tier_resolved_model(
    agent: Any,
    mid: str,
    user_message: str,
    opm_meta: Dict[str, Any],
) -> str:
    """Under OPM, never keep a per-turn pick on disallowed-family ids, Gemini API slugs, or other free stacks.

    Misconfigured ``tier_models``, blocklist replacements, or missed tier upgrades can
    still yield wrong Google-stack slugs. Without this clamp,
    ``_reconcile_runtime_after_tier_model_change`` may leave the Gemini snapshot
    while the model id is wrong, or keep the subagent on a free tier despite OPM.
    """
    if not mid or opm_manual_override_active(agent) or not opm_enabled(agent):
        return mid
    mlow = str(mid).lower()
    try:
        from agent.subprocess_governance import classify_model_cost

        cost = classify_model_cost(mid)
    except Exception:
        cost = "paid"
    google_stack = model_id_contains_disallowed_family(mid) or "gemini" in mlow
    if cost != "free" and not google_stack:
        return mid
    try:
        opm_cfg, _ = resolve_openai_primary_mode(agent)
        coding = any(
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
        trivial = trivial_message_skips_opm_tier_uplift(user_message)
        if trivial and not coding:
            from agent.opm_quota_ladder import (
                cheapest_opm_native_chat_slug,
                format_opm_native_slug_for_agent,
            )

            cheap = cheapest_opm_native_chat_slug()
            if cheap:
                repl = format_opm_native_slug_for_agent(agent, cheap)
            else:
                repl = ""
        else:
            repl = str(
                (opm_cfg.get("codex_model") if coding else opm_cfg.get("default_model")) or ""
            ).strip()
        if not repl or model_id_contains_disallowed_family(repl):
            repl = opm_auxiliary_model(agent)
        if repl and not model_id_contains_disallowed_family(repl):
            logger.info("openai_primary_mode: clamping tier-mapped model %r → %r", mid, repl)
            return repl
    except Exception:
        logger.debug("openai_primary_mode tier clamp failed", exc_info=True)
    return mid


def _opm_turn_needs_native_openai_fix(agent: Any, mid: str) -> bool:
    """True when this turn should be forced onto native OpenAI under OPM."""
    m = (mid or "").strip()
    if not m:
        return True
    low = m.lower()
    if model_id_contains_disallowed_family(m) or "gemini" in low:
        return True
    try:
        from agent.subprocess_governance import classify_model_cost

        p = str(getattr(agent, "provider", None) or "")
        bu = str(getattr(agent, "base_url", None) or "")
        if classify_model_cost(m, provider=p, base_url=bu) == "free":
            return True
    except Exception:
        pass
    try:
        from agent.openai_native_runtime import is_native_openai_consultant_model_id

        if is_native_openai_consultant_model_id(m):
            bu = (getattr(agent, "base_url", None) or "").lower()
            if "api.openai.com" not in bu:
                return True
    except Exception:
        pass
    return False


def enforce_opm_runtime_after_per_turn_routing(agent: Any, user_message: str) -> None:
    """Last-line OPM enforcement after :func:`apply_per_turn_tier_model`.

    Catches early returns inside per-turn routing (``_model_is_tier_routed`` off,
    no runtime cfg on first init path, etc.), wrong HTTP stack for a GPT slug, or
    any remaining disallowed-family / Gemini / free model id before the first LLM call.
    """
    try:
        if getattr(agent, "_defer_opm_primary_coercion", False):
            return
        if not opm_enabled(agent):
            return
        cur = (getattr(agent, "model", None) or "").strip()
        disallowed_only = model_id_contains_disallowed_family(cur)
        if not disallowed_only and not _opm_turn_needs_native_openai_fix(agent, cur):
            return
        opm_cfg, _ = resolve_openai_primary_mode(agent)
        coding = any(
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
        trivial = trivial_message_skips_opm_tier_uplift(user_message)
        if trivial and not coding:
            from agent.opm_quota_ladder import (
                cheapest_opm_native_chat_slug,
                format_opm_native_slug_for_agent,
            )

            cheap = cheapest_opm_native_chat_slug()
            new_mid = (
                format_opm_native_slug_for_agent(agent, cheap) if cheap else ""
            ).strip()
        else:
            new_mid = str(
                (opm_cfg.get("codex_model") if coding else opm_cfg.get("default_model")) or ""
            ).strip()
        if (not new_mid or model_id_contains_disallowed_family(new_mid)) and disallowed_only:
            new_mid = opm_auxiliary_model(agent)
        elif not new_mid:
            return
        if model_id_contains_disallowed_family(new_mid):
            return
        logger.info("openai_primary_mode: turn enforcement %r → %r", cur or "(empty)", new_mid)
        agent.model = new_mid
        reb = getattr(agent, "_reconcile_runtime_after_tier_model_change", None)
        if callable(reb):
            reb()
    except Exception:
        logger.debug("enforce_opm_runtime_after_per_turn_routing failed", exc_info=True)


def apply_per_turn_tier_model(agent: Any, user_message: str) -> None:
    """Optional per-turn model pick from ``tier_models`` (dynamic tier routing)."""
    # Prime OPM metadata for main_turn_selection traces even when we return early below.
    try:
        _, agent._last_opm_meta = resolve_openai_primary_mode(agent)
    except Exception:
        agent._last_opm_meta = getattr(agent, "_last_opm_meta", None) or {}
    # `/models` pipeline selection: honor user pick for this turn (see run_agent.AIAgent).
    if getattr(agent, "_skip_per_turn_tier_routing", False):
        return
    # Stay on the active provider/model while provider fallback is pinned (e.g. rate limits).
    # Exception: when the runtime is OpenRouter (including OPM cross-provider failover to
    # openai/… slugs), still run per-turn tier routing so tier_models can vary mini vs full
    # each turn. Non-OR fallbacks (e.g. direct Gemini) stay pinned to avoid oscillation.
    if getattr(agent, "_fallback_activated", False):
        try:
            or_runtime = bool(getattr(agent, "_is_openrouter_url", lambda: False)())
        except Exception:
            or_runtime = False
        if not or_runtime:
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

    _opm_meta = getattr(agent, "_last_opm_meta", None) or {}
    # Cost policy: do **not** force A/B/C → E/F under OPM. Stay on the deterministic /
    # consultant tier so route-down (cheap) tiers are actually used; escalate only via
    # pushback, consultant routing, or explicit [HERMES_ESCALATE] / quota ladders.

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

    # No post-consultant OPM uplift to E/F — same cheapest-first policy as above.

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
            "before launching subprocess; only free local models (local inference or local/ slugs) permitted "
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
    mid = _opm_clamp_tier_resolved_model(agent, str(mid), user_message, _opm_meta)
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

    emit_routing_decision_trace(
        stage="per_turn_tier_override",
        chosen_model=str(mid or ""),
        chosen_provider=str(getattr(agent, "provider", "") or ""),
        reason_code="tier_selected",
        opm_enabled=bool(_opm_meta.get("enabled", False)),
        opm_source=str(_opm_meta.get("source", "")),
        tier_source=f"deterministic:{deterministic_tier}",
        skip_flags={
            "skip_per_turn": bool(getattr(agent, "_skip_per_turn_tier_routing", False)),
            "fallback_activated": bool(getattr(agent, "_fallback_activated", False)),
            "model_is_tier_routed": bool(getattr(agent, "_model_is_tier_routed", True)),
        },
        fallback_activated=bool(getattr(agent, "_fallback_activated", False)),
        explicit_user_model=not bool(getattr(agent, "_model_is_tier_routed", True)),
        profile=str(getattr(agent, "profile", "") or ""),
        session_id=str(getattr(agent, "session_id", "") or ""),
    )

    # Native OpenAI consultant tiers need api.openai.com + OPENAI_API_KEY; restore baseline otherwise.
    _rebind = getattr(agent, "_reconcile_runtime_after_tier_model_change", None)
    if callable(_rebind):
        try:
            _rebind()
        except Exception:
            logger.debug("tier model runtime reconcile failed", exc_info=True)
