"""Workspace token-governance runtime caps (activation Session 6+).

If ``HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml`` exists
and ``enabled: true``, Hermes applies model downgrade rules, iteration caps, optional
``skip_context_files``, and delegation iteration caps on every :class:`~run_agent.AIAgent`
construction.

Disable entirely with ``HERMES_TOKEN_GOVERNANCE_DISABLE=1``. Allow blocked (premium)
models to pass through with ``HERMES_GOVERNANCE_ALLOW_PREMIUM=1``.
"""

from __future__ import annotations

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


def apply_token_governance_runtime(agent: Any) -> None:
    """Apply governance caps to a freshly constructed ``AIAgent`` (mutates in place)."""
    cfg = load_runtime_config()
    if not cfg:
        return

    mlow = (agent.model or "").lower()
    allow_premium = os.environ.get(ENV_ALLOW_PREMIUM, "").strip().lower() in ("1", "true", "yes")

    blocked = cfg.get("blocked_model_substrings") or []
    if isinstance(blocked, str):
        blocked = [blocked]
    default_model = (cfg.get("default_model") or "").strip()

    if not allow_premium and default_model and blocked:
        for sub in blocked:
            if sub and str(sub).lower() in mlow:
                logger.warning(
                    "Token governance: model %r matches blocked substring %r; using default_model %r "
                    "(set %s=1 to keep configured model).",
                    agent.model,
                    sub,
                    default_model,
                    ENV_ALLOW_PREMIUM,
                )
                agent.model = default_model
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

    # Recompute prompt caching flags if model changed (mirrors run_agent.AIAgent.__init__)
    try:
        is_openrouter = agent._is_openrouter_url()
        is_claude = "claude" in (agent.model or "").lower()
        is_native_anthropic = agent.api_mode == "anthropic_messages"
        agent._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
    except Exception:
        logger.debug("token governance: could not refresh prompt caching flags", exc_info=True)
