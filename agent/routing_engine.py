"""Unified routing engine — single GPT-5.4 call per prompt.

Replaces the separate ``profile_router`` + ``consultant_router`` LLM calls with
one authoritative GPT-5.4 decision that covers:

  - **tier** (A–F): model tier matched to genuine prompt complexity
  - **profile**: most suitable named profile, or ``None`` for chief-orchestrator
  - **free_model_brief**: concise, machine-readable instruction optimised for
    free-tier models (tiers A/B/C) so limited models perform well
  - **coding_task**: hint that tier-F (gpt-5.3-codex) is preferred when escalating

GPT-5.4 is used as the router because it produces genuinely dynamic, non-static
decisions rather than falling back to the same model every turn. Gemini Flash
is the fallback when no OpenAI key is available.

Called by ``agent/consultant_routing.py`` → ``agent/token_governance_runtime.py``
on every user turn when token-governance is active.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TIER_LETTERS = frozenset("ABCDEFG")

# ---------------------------------------------------------------------------
# Route decision dataclass
# ---------------------------------------------------------------------------


@dataclass
class UnifiedRouteDecision:
    """Routing decision returned by ``route_prompt``."""

    tier: str = "D"
    """Recommended tier letter (A–F). All tiers involve API costs."""

    profile: Optional[str] = None
    """Named profile to delegate to, or None for chief-orchestrator/default."""

    free_model_brief: Optional[str] = None
    """Concise machine-readable brief for low-cost-tier (A/B/C) models.
    None when tier D/E/F (full-capability models need no brief).
    Field kept as free_model_brief for backwards compatibility."""

    coding_task: bool = False
    """True when the request is primarily software/engineering work.
    Used to prefer tier F (gpt-5.3-codex) on consultant escalation."""

    background_task: bool = False
    """True when the request explicitly involves a background/subprocess task.
    Background tasks must use only free local models (gemma-4-31b-it or local inference).
    Chief orchestrator must be consulted before any paid background task launches."""

    audit: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routing prompt
# ---------------------------------------------------------------------------

_ROUTING_SYSTEM_PROMPT = """\
You are the Hermes routing advisor. For every user request you make ONE authoritative \
JSON routing decision that covers model tier selection, profile delegation, and (for \
low-cost tiers) a condensed task brief.

TIER TABLE (ascending capability/cost — ALL tiers cost money via API):
  A = Gemini Flash       — one-liners, trivial ack/lookup, pure formatting (low-cost)
  B = Gemini Flash-Lite  — short/simple tasks, renames, single-file edits (low-cost)
  C = Gemini Pro         — multi-step reasoning, moderate complexity, analysis (low-cost)
  D = claude-sonnet-4.6  — complex tasks, most consultations, writing, planning, debugging
  E = gpt-5.4            — hardest non-coding reasoning, ambiguous multi-domain problems
  F = gpt-5.3-codex      — deep engineering, architecture, refactors, complex codegen

COST HIERARCHY (cheapest to most expensive):
  FREE:     gemma-4-31b-it via direct Google Gemini API, self-hosted local inference
  LOW-COST: Gemini Flash/Pro via direct Google API (tiers A/B/C)
  PAID:     ANY model routed via OpenRouter (including gemma-4-31b-it on OpenRouter)
  HIGH:     claude-sonnet-4.6, gpt-5.4, gpt-5.3-codex, claude-opus-4.6

CRITICAL: OpenRouter is ALWAYS paid — even for models that are free via their native API.
Always prefer the direct API source (Google for Gemini/Gemma, OpenAI for GPT, Anthropic for \
Claude) before falling back to OpenRouter. OpenRouter is a last resort when direct APIs fail.

ROUTING RULES:
1. Match tier strictly to genuine complexity. NEVER default to D unless the task is complex.
   Use A/B/C for the bulk of routine/menial work — they have the lowest API cost.
2. Optimize for the lowest cost at the highest performance the task requires.
   Under-routing cost is always lower than over-routing.
3. Escalate to D only when depth/quality genuinely warrants it (most complex tasks).
4. Escalate to E/F only for the hardest tasks or after repeated failures.
5. coding_task=true when the primary work is software engineering (prefers F for consultant
   escalation over E). This also hints to use gpt-5.3-codex for any code-heavy background work.
6. low_cost_brief: REQUIRED when tier is A, B, or C. Write a direct, concise,
   machine-readable restatement of the task optimised for a capable-but-limited model.
   Use imperative sentences. Max 3 sentences. Omit pleasantries.
7. low_cost_brief must be null when tier is D, E, or F.
8. profile: suggest the most suitable profile by EXACT name, or null for default.
9. background_task: true if the request explicitly asks to run something in the background,
   spawn a subprocess, or run a parallel process. Background tasks MUST use only free
   models (gemma-4-31b-it via direct Gemini API, local inference) — any paid model \
requires operator approval.

PROFILES:
{profiles_desc}

Return ONLY valid JSON — no markdown fences, no prose:
{{
  "tier": "A" | "B" | "C" | "D" | "E" | "F",
  "profile": "<exact_profile_name>" | null,
  "coding_task": true | false,
  "background_task": true | false,
  "low_cost_brief": "<concise instruction for low-cost model>" | null
}}
"""

_ROUTING_USER_TMPL = """\
User request:
{user_message}

Recent context (last 2 turns):
{context_summary}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarise_context(messages: Optional[List[dict]], max_chars: int = 400) -> str:
    if not messages:
        return "(no prior context)"
    parts: list[str] = []
    for m in messages[-4:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue
        c = m.get("content")
        if isinstance(c, str):
            parts.append(f"{role}: {c[:200]}")
        elif isinstance(c, list):
            for blk in c:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    t = blk.get("text", "")
                    if t:
                        parts.append(f"{role}: {t[:200]}")
                    break
    summary = "\n".join(parts)
    return (summary[:max_chars] if summary else "(no prior context)")


def _profiles_description(available_profiles: Optional[List[str]]) -> str:
    if not available_profiles:
        return "No named profiles available — always use null."
    return (
        "Available profiles: " + ", ".join(available_profiles) + ".\n"
        "Use null to stay with chief-orchestrator/default."
    )


def _parse_routing_response(raw: str) -> Optional[dict]:
    """Extract and validate JSON from the routing LLM response."""
    if not raw:
        return None
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    tier = str(obj.get("tier") or "D").strip().upper()
    if tier not in _TIER_LETTERS:
        tier = "D"
    profile = obj.get("profile") or None
    if isinstance(profile, str):
        profile = profile.strip() or None
    # Accept both new "low_cost_brief" key and legacy "free_model_brief"
    brief = obj.get("low_cost_brief") or obj.get("free_model_brief") or None
    if isinstance(brief, str):
        brief = brief.strip() or None
    # Brief only applies to low-cost tiers A/B/C
    if tier not in ("A", "B", "C"):
        brief = None
    return {
        "tier": tier,
        "profile": profile,
        "coding_task": bool(obj.get("coding_task", False)),
        "background_task": bool(obj.get("background_task", False)),
        "free_model_brief": brief,
    }


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def _call_routing_llm(system: str, user: str) -> str:
    """Call GPT-5.4 via native OpenAI (preferred) or Gemini Flash (fallback)."""
    from agent.auxiliary_client import call_llm, extract_content_or_reasoning
    from agent.openai_native_runtime import native_openai_runtime_tuple

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Primary: native OpenAI GPT-5.4 — highest routing quality
    _rt = native_openai_runtime_tuple()
    bt, ak = _rt if _rt else (None, None)
    if bt and ak:
        try:
            resp = call_llm(
                task=None,
                provider="custom",
                model="gpt-5.4",
                base_url=bt,
                api_key=ak,
                messages=msgs,
                temperature=0.1,
                max_tokens=300,
            )
            result = extract_content_or_reasoning(resp) or ""
            if result:
                logger.debug("routing_engine: GPT-5.4 routing OK")
                return result
        except Exception as exc:
            logger.debug("routing_engine: GPT-5.4 failed, trying fallback: %s", exc)

    # Fallback: Gemini Flash (free, fast)
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key:
        try:
            resp = call_llm(
                task=None,
                provider="gemini",
                model="gemini-2.5-flash",
                messages=msgs,
                temperature=0.1,
                max_tokens=300,
            )
            result = extract_content_or_reasoning(resp) or ""
            if result:
                logger.debug("routing_engine: Gemini Flash fallback routing OK")
                return result
        except Exception as exc:
            logger.debug("routing_engine: Gemini Flash fallback failed: %s", exc)

    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route_prompt(
    user_message: str,
    *,
    available_profiles: Optional[List[str]] = None,
    conversation_messages: Optional[List[dict]] = None,
    fallback_tier: str = "D",
) -> UnifiedRouteDecision:
    """Make a unified routing decision for a single user prompt.

    Uses GPT-5.4 (native OpenAI) as the primary router — it produces genuinely
    dynamic decisions rather than static fallbacks. Gemini Flash is the fallback.

    Returns an ``UnifiedRouteDecision`` with:
    - tier: A–F matched to prompt complexity
    - profile: named profile or None
    - free_model_brief: condensed brief for free-tier models (A/B/C only)
    - coding_task: hint for tier-F preference when escalating
    """
    profiles_desc = _profiles_description(available_profiles)
    system_prompt = _ROUTING_SYSTEM_PROMPT.format(profiles_desc=profiles_desc)
    context_summary = _summarise_context(conversation_messages)
    user_prompt = _ROUTING_USER_TMPL.format(
        user_message=(user_message or "")[:800],
        context_summary=context_summary,
    )

    raw = ""
    try:
        raw = _call_routing_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("routing_engine: LLM call raised: %s", exc)

    parsed = _parse_routing_response(raw) if raw else None
    if parsed:
        brief = parsed.get("free_model_brief")
        # If brief is missing for a low-cost tier, synthesise a minimal one
        if parsed["tier"] in ("A", "B", "C") and not brief:
            brief = (user_message or "").strip()[:400] or None
        return UnifiedRouteDecision(
            tier=parsed["tier"],
            profile=parsed.get("profile"),
            free_model_brief=brief,
            coding_task=parsed.get("coding_task", False),
            background_task=parsed.get("background_task", False),
            audit={"raw_excerpt": raw[:300], "parsed": True},
        )

    # Fallback: return deterministic tier without brief
    return UnifiedRouteDecision(
        tier=fallback_tier,
        audit={"raw_excerpt": raw[:100] if raw else "", "parsed": False},
    )


# ---------------------------------------------------------------------------
# Summary review (post-response alignment check)
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM = (
    "You are a quality reviewer. Compare the user's original request with the "
    "agent's final response summary. Respond ONLY with JSON:\n"
    '{"aligned": true} if the response addresses the request, OR\n'
    '{"aligned": false, "reason": "one sentence", '
    '"action": "reroute"} if fundamentally misaligned, failed, or blocked.'
)


def review_agent_summary(
    user_prompt_excerpt: str,
    agent_response_excerpt: str,
    current_tier: str = "",
    current_model: str = "",
) -> Dict[str, Any]:
    """Ultra-concise post-response alignment check using the free model.

    Returns ``{"aligned": True}`` on success or review failure (fail-open).
    Returns ``{"aligned": False, "reason": "...", "action": "reroute"}`` on
    misalignment.

    Total budget: ~500 input tokens, ~50 output tokens.
    """
    user_snip = (user_prompt_excerpt or "")[:300]
    resp_snip = (agent_response_excerpt or "")[:200]

    if not user_snip.strip() or not resp_snip.strip():
        return {"aligned": True}

    user_msg = (
        f"User request (first 300 chars):\n{user_snip}\n\n"
        f"Agent response (last 200 chars):\n{resp_snip}\n\n"
        f"Current tier: {current_tier}, model: {current_model}"
    )

    try:
        from agent.auxiliary_client import call_llm

        raw = call_llm(
            prompt=user_msg,
            system=_REVIEW_SYSTEM,
            model="gemma-4-31b-it",
            provider="gemini",
            max_tokens=60,
            temperature=0.0,
        )
        text = (raw or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            obj = json.loads(m.group())
            return {
                "aligned": bool(obj.get("aligned", True)),
                "reason": str(obj.get("reason", ""))[:200],
                "action": str(obj.get("action", ""))[:20],
            }
    except Exception as exc:
        logger.debug("review_agent_summary failed: %s", exc)

    return {"aligned": True}
