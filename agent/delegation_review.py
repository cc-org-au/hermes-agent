"""Delegation context review and model gating.

Before a delegated agent runs, this module:
1. Reviews the delegation context for sufficiency (using a free model).
2. Ensures delegated agents use cheaper-or-equal models vs the parent.
3. Blocks consultant-tier models for delegated agents.

All review calls use the free model (gemma-4-31b-it via Gemini API) to
keep overhead at zero cost.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_COST_RANK = {
    "free": 0,
    "low_cost": 1,
    "paid": 2,
}

_CONSULTANT_TIER_SUBSTRINGS = (
    "opus",
    "gpt-5.4",
    "gpt-5.3-codex",
)

_MAX_DELEGATE_TIER = "D"


def is_consultant_tier_model(model_id: str) -> bool:
    """True if the model is in the consultant tier (should not be used by delegates)."""
    mid = (model_id or "").strip().lower()
    return any(s in mid for s in _CONSULTANT_TIER_SUBSTRINGS)


def gate_delegate_model(
    proposed_model: str,
    parent_model: str,
) -> Tuple[str, str]:
    """Enforce model gating for delegated agents.

    Returns ``(approved_model, reason)`` — the model may be downgraded.
    """
    from agent.subprocess_governance import classify_model_cost, default_free_subprocess_model_id

    if is_consultant_tier_model(proposed_model):
        free = default_free_subprocess_model_id()
        return free, f"consultant model {proposed_model!r} blocked for delegates; using {free}"

    parent_cost = _COST_RANK.get(classify_model_cost(parent_model), 2)
    child_cost = _COST_RANK.get(classify_model_cost(proposed_model), 2)

    if child_cost > parent_cost:
        free = default_free_subprocess_model_id()
        return free, (
            f"delegate model {proposed_model!r} more expensive than parent "
            f"{parent_model!r}; downgraded to {free}"
        )

    return proposed_model, "approved"


def review_delegation_context(
    goal: str,
    context: Optional[str],
    proposed_model: str,
) -> Dict[str, Any]:
    """Quick review of delegation context using the free model.

    Returns a dict with ``approved`` (bool), optional ``improved_context``,
    and optional ``model_override``.

    On any failure returns ``{"approved": True}`` (fail-open).
    """
    if not goal or not goal.strip():
        return {"approved": True, "note": "empty goal — skipped review"}

    snippet = (goal[:200] + "..." if len(goal) > 200 else goal)
    ctx_snippet = ""
    if context:
        ctx_snippet = context[:150] + ("..." if len(context) > 150 else "")

    prompt = (
        "You are a delegation reviewer. Evaluate if the context below is "
        "sufficient for a sub-agent to complete the goal. Respond ONLY with "
        'a JSON object: {"approved": true} or {"approved": true, '
        '"improved_context": "one sentence of additional guidance"}.\n\n'
        f"Goal: {snippet}\n"
    )
    if ctx_snippet:
        prompt += f"Context: {ctx_snippet}\n"
    prompt += f"Model: {proposed_model}\n"

    try:
        from agent.auxiliary_client import call_llm

        raw = call_llm(
            prompt=prompt,
            model="gemma-4-31b-it",
            provider="gemini",
            max_tokens=80,
            temperature=0.0,
        )
        text = (raw or "").strip()
        if text.startswith("{"):
            return json.loads(text)
    except Exception as exc:
        logger.debug("delegation review call failed: %s", exc)

    return {"approved": True}
