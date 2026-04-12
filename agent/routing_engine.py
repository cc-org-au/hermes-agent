"""Unified routing engine — one cheap LLM JSON decision per prompt.

Chooses tier (A–G), profile, and brief using **cheapest-first** policy: routing calls
prefer gpt-5-nano / gpt-4.1-nano / gpt-5.4-nano before any flagship. The catalog
digest is sorted by estimated API cost so advisors see the full model spectrum.

Called from ``agent/consultant_routing.py`` → ``agent/token_governance_runtime.py``
when token-governance is active.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.openai_primary_mode import resolve_openai_primary_mode
from agent.provider_model_routing_catalog import format_routing_catalog_digest
from agent.routing_trace import emit_routing_decision_trace
from agent.trivial_prompt import trivial_message_skips_opm_tier_uplift

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
    Background tasks must use only free local models (Gemini Flash via direct API or local inference).
    Chief orchestrator must be consulted before any paid background task launches."""

    audit: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routing prompt
# ---------------------------------------------------------------------------

_ROUTING_SYSTEM_PROMPT = """\
You are the Hermes routing advisor. Your job is to pick the **lowest tier** that can \
plausibly satisfy the user, using the attached catalog (sorted cheapest-first). You only \
output JSON — you do **not** run the final user-facing reply; execution uses tier_models.

TIER TABLE (ascending capability/cost — prefer lower letters; ALL tiers may bill):
  A = ultra-cheap: gpt-5-nano, gpt-4.1-nano, gpt-5.4-nano (routing, classification, pings)
  B = cheap capable: gpt-5-mini, gpt-4.1-mini, gpt-5.4-mini (drafts, short edits, simple Q&A)
  C = mid: gpt-5.2, gpt-4.1, Gemini Flash-class (multi-step but not frontier)
  D = strong generalist: e.g. Sonnet-class / gpt-5.4 only when C is insufficient
  E = consultant / hardest reasoning (requires deliberation + approval in Hermes — pick rarely)
  F = deep coding / Codex-class (requires deliberation path for consultant work — pick rarely)
  G = reserved for chief/consultant ceiling (opus-class) — almost never from this router alone

CONSULTANT / FRONTIER RULE:
- Tiers **E, F, G** are for **routing guidance only** here: choose them only when the task \
clearly needs frontier reasoning or production-critical codegen **and** a cheaper tier is \
unlikely to suffice. Hermes may still require explicit deliberation/approval before those \
models generate user-visible output.

CHEAPEST-FIRST (mandatory):
1. Default the majority of turns to **A, B, or C**. Use **D** only when the prompt needs \
substantial reasoning, long context nuance, or multi-file coherence that cheaper tiers lack.
2. Never “default high” to save thinking — **under-routing saves money**; escalation exists \
for failures and pushback.
3. coding_task=true suggests **F** only for heavy engineering; otherwise prefer **C or D** \
with cheaper models before Codex.
4. low_cost_brief: REQUIRED when tier is A, B, or C (imperative, ≤3 short sentences).
5. low_cost_brief null for D–G.
6. background_task=true → prefer tier **A** and the budget nano class; never jump to E/F \
for background work.

PROFILES:
{profiles_desc}

Return ONLY valid JSON — no markdown fences, no prose:
{{
  "tier": "A" | "B" | "C" | "D" | "E" | "F" | "G",
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
    tier = str(obj.get("tier") or "B").strip().upper()
    if tier not in _TIER_LETTERS:
        tier = "B"
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
    """Cheapest routing LLM first (classification JSON only); expensive models last."""
    from agent.auxiliary_client import call_llm, extract_content_or_reasoning
    from agent.openai_native_runtime import native_openai_runtime_tuple

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    _rt = native_openai_runtime_tuple()
    bt, ak = _rt if _rt else (None, None)

    def _try_native(model_id: str, label: str) -> Optional[str]:
        if not bt or not ak:
            return None
        try:
            resp = call_llm(
                task=None,
                provider="custom",
                model=model_id,
                base_url=bt,
                api_key=ak,
                messages=msgs,
                temperature=0.1,
                max_tokens=320,
            )
            result = extract_content_or_reasoning(resp) or ""
            if result:
                logger.debug("routing_engine: %s routing OK", label)
                return result
        except Exception as exc:
            logger.debug("routing_engine: %s failed: %s", label, exc)
        return None

    # Native API: cheapest first (catalog: gpt-5-nano < gpt-4.1-nano < gpt-5.4-nano < …)
    for mid, lab in (
        ("gpt-5-nano", "gpt-5-nano"),
        ("gpt-4.1-nano", "gpt-4.1-nano"),
        ("gpt-5.4-nano", "gpt-5.4-nano"),
        ("gpt-5-mini", "gpt-5-mini"),
    ):
        out = _try_native(mid, lab)
        if out:
            return out

    # OpenRouter hub (same order idea)
    for or_model, lab in (
        ("openai/gpt-5-nano", "OR gpt-5-nano"),
        ("openai/gpt-4.1-nano", "OR gpt-4.1-nano"),
        ("openai/gpt-5.4-nano", "OR gpt-5.4-nano"),
        ("openai/gpt-5-mini", "OR gpt-5-mini"),
    ):
        try:
            resp = call_llm(
                task=None,
                provider="openrouter",
                model=or_model,
                messages=msgs,
                temperature=0.1,
                max_tokens=320,
            )
            result = extract_content_or_reasoning(resp) or ""
            if result:
                logger.debug("routing_engine: %s routing OK", lab)
                return result
        except Exception as exc:
            logger.debug("routing_engine: %s failed: %s", lab, exc)

    # Quality last resort for JSON routing only (still cheaper than running the main agent on 5.4)
    if bt and ak:
        try:
            resp = call_llm(
                task=None,
                provider="custom",
                model="gpt-5.4-mini",
                base_url=bt,
                api_key=ak,
                messages=msgs,
                temperature=0.1,
                max_tokens=320,
            )
            result = extract_content_or_reasoning(resp) or ""
            if result:
                logger.debug("routing_engine: gpt-5.4-mini routing OK")
                return result
        except Exception as exc:
            logger.debug("routing_engine: gpt-5.4-mini failed: %s", exc)

    # Last: Gemini Flash (direct API)
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

    logger.warning(
        "routing_engine: all routing LLM options failed — using deterministic fallback tier"
    )
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route_prompt(
    user_message: str,
    *,
    available_profiles: Optional[List[str]] = None,
    conversation_messages: Optional[List[dict]] = None,
    fallback_tier: str = "B",
) -> UnifiedRouteDecision:
    """Make a unified routing decision for a single user prompt (cheapest tier first).

    Router LLM calls use budget-class models only; OPM does **not** force tier E/F.
    Fallback when parsing fails is **B** (not D/E).

    Returns an ``UnifiedRouteDecision`` with:
    - tier: A–G matched to prompt complexity
    - profile: named profile or None
    - free_model_brief: condensed brief for A/B/C
    - coding_task: hint for tier-F when truly needed
    """
    opm_cfg, opm_meta = resolve_openai_primary_mode(None)
    opm = opm_cfg if opm_meta.get("enabled", False) else None

    profiles_desc = _profiles_description(available_profiles)
    system_prompt = _ROUTING_SYSTEM_PROMPT.format(profiles_desc=profiles_desc)
    _cat = format_routing_catalog_digest()
    if _cat:
        system_prompt += (
            "\n\nMULTI-PROVIDER MODEL CATALOG (rows ordered **cheapest first** by estimated "
            "USD/MTok input; use for fit vs tier A–G):\n"
            + _cat
        )

    if opm:
        system_prompt += (
            "\n\nOPENAI PRIMARY MODE ACTIVE: Still **default low** — prefer tiers A/B/C for "
            "typical chat and tooling; use D only when needed; reserve E/F/G for clear "
            "frontier need. Subprocess/cron budget class remains nano-tier unless approved."
        )

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

        tier = parsed["tier"]
        coding_task = parsed.get("coding_task", False)

        if opm and trivial_message_skips_opm_tier_uplift(user_message) and tier in (
            "D",
            "E",
            "F",
            "G",
        ):
            tier = "A"
            coding_task = False

        decision = UnifiedRouteDecision(
            tier=tier,
            profile=parsed.get("profile"),
            free_model_brief=brief,
            coding_task=coding_task,
            background_task=parsed.get("background_task", False),
            audit={"raw_excerpt": raw[:300], "parsed": True,
                   "openai_primary_mode": bool(opm)},
        )
        emit_routing_decision_trace(
            stage="main_route_selection",
            chosen_model=f"tier:{decision.tier}",
            chosen_provider="routing_engine",
            reason_code="llm_parsed",
            opm_enabled=bool(opm),
            opm_source=str(opm_meta.get("source", "")),
            tier_source="router_llm",
            fallback_activated=False,
            explicit_user_model=False,
        )
        return decision

    _fb = fallback_tier
    emit_routing_decision_trace(
        stage="main_route_selection",
        chosen_model=f"tier:{_fb}",
        chosen_provider="routing_engine",
        reason_code="llm_parse_fallback",
        opm_enabled=bool(opm),
        opm_source=str(opm_meta.get("source", "")),
        tier_source="fallback_tier",
        fallback_activated=False,
        explicit_user_model=False,
    )
    return UnifiedRouteDecision(
        tier=_fb,
        audit={"raw_excerpt": raw[:100] if raw else "", "parsed": False,
               "openai_primary_mode": bool(opm)},
    )


# ---------------------------------------------------------------------------
# Summary review (post-response alignment check)
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM = (
    "You are a quality reviewer. Compare the user's original request with the "
    "agent's final response summary. Respond ONLY with JSON:\n"
    '{"aligned": true} if the response addresses the request, OR\n'
    '{"aligned": false, "reason": "one sentence", '
    '"action": "reroute"} if fundamentally misaligned, failed, or blocked.\n\n'
    "IMPORTANT: If the response contains any indication that the agent SIMULATED, "
    "STUBBED, FAKED, or MOCKED actions instead of performing them for real — such as "
    "writing scripts that print fake status messages, creating dummy files to pretend "
    "work was done, or commenting 'In a real scenario...' — mark it as MISALIGNED "
    "with reason 'agent simulated instead of performing real actions'."
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
        from agent.auxiliary_client import call_llm, extract_content_or_reasoning
        from agent.openai_primary_mode import opm_enabled, opm_auxiliary_model

        _m = "openai/gpt-5.4-nano"
        _p = "openrouter"
        if opm_enabled(None):
            _m = opm_auxiliary_model(None)
        ml = (_m or "").lower()
        if "gemini" in ml and "gpt" not in ml:
            _p = "gemini"
        elif "/" in ml or ml.startswith("openai/"):
            _p = "openrouter"
        else:
            _p = "custom"
        resp = call_llm(
            task=None,
            provider=_p,
            model=_m,
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        text = (extract_content_or_reasoning(resp) or "").strip()
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
