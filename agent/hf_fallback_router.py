"""Tier routing: pick one HF hub model id from configured tiers.

- ``resolve_hf_routed_model`` — Hugging Face ``router.huggingface.co`` OpenAI-compatible API.
- ``resolve_gemini_routed_model`` — same JSON contract via Google AI (e.g. ``gemma-4-31b-it``).

Model IDs come from configuration (``free_model_routing`` / ``fallback_providers``).

Set ``HERMES_HF_ROUTER_DISABLE=1`` to skip the tiered router and use that entry's ``model`` field as-is.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from agent.tier_model_routing import canonical_gemma_model_id

logger = logging.getLogger(__name__)


def _opm_clamp_routed_model(selected: str, routing_agent: Any) -> str:
    """Never return a Gemma id when openai_primary_mode is enabled."""
    try:
        from agent.openai_primary_mode import (
            is_gemma_model_id,
            opm_blocks_gemma,
            opm_non_gemma_replacement_model,
        )

        if not opm_blocks_gemma(routing_agent):
            return selected
        if not is_gemma_model_id(selected):
            return selected
        return opm_non_gemma_replacement_model(routing_agent)
    except Exception:
        return selected


def _flatten_tier_models(tiers: List[Dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for t in tiers:
        for m in t.get("models") or []:
            s = str(m).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def first_tier_hub_fallback(
    tiers: List[Dict[str, Any]],
    router_model: str,
    routing_agent: Any = None,
) -> str:
    """First hub id in tier order; else *router_model*. Under OPM, skip Gemma tier targets."""
    flat = _flatten_tier_models(tiers)
    try:
        from agent.openai_primary_mode import (
            is_gemma_model_id,
            opm_blocks_gemma,
            opm_non_gemma_replacement_model,
        )

        if opm_blocks_gemma(routing_agent):
            for m in flat:
                if m and not is_gemma_model_id(m):
                    return m
            return opm_non_gemma_replacement_model(routing_agent)
    except Exception:
        pass
    return flat[0] if flat else router_model


def resolve_gemini_routed_model(
    user_text: str,
    *,
    router_model: str,
    tiers: List[Dict[str, Any]],
    routing_agent: Any = None,
) -> str:
    """Pick one hub id from *tiers* using Google AI (Gemini / Gemma API) *router_model*.

    Uses ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``. Same JSON shape as the HF router path.
    """
    router_model = canonical_gemma_model_id((router_model or "").strip())
    try:
        from agent.openai_primary_mode import (
            is_gemma_model_id,
            opm_blocks_gemma,
            opm_non_gemma_replacement_model,
        )

        if opm_blocks_gemma(routing_agent) and is_gemma_model_id(router_model):
            router_model = opm_non_gemma_replacement_model(routing_agent)
    except Exception:
        pass
    if os.environ.get("HERMES_HF_ROUTER_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return _opm_clamp_routed_model(
            first_tier_hub_fallback(tiers, router_model, routing_agent=routing_agent),
            routing_agent,
        )

    if not tiers:
        return _opm_clamp_routed_model(router_model, routing_agent)

    flat = _flatten_tier_models(tiers)
    fallback = first_tier_hub_fallback(tiers, router_model, routing_agent=routing_agent)
    if not router_model.strip():
        return _opm_clamp_routed_model(fallback, routing_agent)

    tier_lines: List[str] = []
    for i, t in enumerate(tiers):
        tid = str(t.get("id") or f"tier-{i}")
        desc = str(t.get("description") or "").strip()
        models = t.get("models") or []
        mstr = ", ".join(models)
        extra = f" — {desc}" if desc else ""
        tier_lines.append(f"Tier {i} [{tid}]{extra}: {mstr}")

    tiers_blob = "\n".join(tier_lines)
    sys_msg = (
        "You route the user message to exactly one Hugging Face hub model id. "
        "These ids refer to checkpoints served locally or on Hugging Face — pick the best fit for this prompt. "
        "Tiers are ordered: lower index = lighter tasks; higher index = heavier reasoning, "
        "math, code, or long agentic work when the prompt requires it. "
        "Pick the minimal tier that fits, then choose the best model id **within that tier** for this specific prompt.\n"
        f"{tiers_blob}\n"
        "Reply with a single JSON object only, no markdown: "
        '{"tier": <int>, "model": "<hub_model_id>"} '
        "The model must appear in that tier's list. tier is the tier index (0-based)."
    )
    user_msg = (user_text or "")[:12000] or "hello"

    try:
        from agent.auxiliary_client import call_llm, extract_content_or_reasoning
    except Exception:
        logger.warning("hf_fallback_router: auxiliary client unavailable")
        return _opm_clamp_routed_model(fallback, routing_agent)

    try:
        resp = call_llm(
            provider="gemini",
            model=router_model.strip(),
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.45,
            max_tokens=200,
        )
        content = extract_content_or_reasoning(resp)
    except Exception as exc:
        logger.info("hf_fallback_router: Gemini router call failed: %s", exc)
        return _opm_clamp_routed_model(fallback, routing_agent)

    picked = _parse_tier_model_json(content, tiers, flat)
    if picked:
        return _opm_clamp_routed_model(picked, routing_agent)
    for c in flat:
        if c in content:
            return _opm_clamp_routed_model(c, routing_agent)
    return _opm_clamp_routed_model(fallback, routing_agent)


def resolve_hf_routed_model(
    user_text: str,
    *,
    api_key: str,
    base_url: str,
    router_model: str,
    tiers: List[Dict[str, Any]],
) -> str:
    """Use *router_model* to pick one hub id from *tiers* for *user_text*.

    *tiers* is the normalized list from ``free_model_routing.normalize_kimi_tiers``.
    On failure, returns the first model of the first tier (if any), else *router_model*.
    """
    router_model = canonical_gemma_model_id((router_model or "").strip())
    if os.environ.get("HERMES_HF_ROUTER_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        flat = _flatten_tier_models(tiers)
        return flat[0] if flat else router_model

    if not tiers:
        return router_model

    flat = _flatten_tier_models(tiers)
    fallback = flat[0] if flat else router_model
    if not router_model.strip():
        return fallback

    tier_lines: List[str] = []
    for i, t in enumerate(tiers):
        tid = str(t.get("id") or f"tier-{i}")
        desc = str(t.get("description") or "").strip()
        models = t.get("models") or []
        mstr = ", ".join(models)
        extra = f" — {desc}" if desc else ""
        tier_lines.append(f"Tier {i} [{tid}]{extra}: {mstr}")

    tiers_blob = "\n".join(tier_lines)
    sys_msg = (
        "You route the user message to exactly one Hugging Face hub model id. "
        "Tiers are ordered: lower index = lighter tasks; higher index = heavier reasoning, "
        "math, code, or long agentic work when the prompt requires it. "
        "Pick the minimal tier that fits, then choose the best model id **within that tier** for this specific prompt. "
        "Do not default to the first model in a tier when another model in the same tier is a better fit. "
        "When several prompts are similar in depth, vary the chosen model across tiers when multiple options apply "
        "so routing is not stuck on one hub id.\n"
        f"{tiers_blob}\n"
        "Reply with a single JSON object only, no markdown: "
        '{"tier": <int>, "model": "<hub_model_id>"} '
        "The model must appear in that tier's list. tier is the tier index (0-based)."
    )
    user_msg = (user_text or "")[:12000] or "hello"

    try:
        from openai import OpenAI
    except Exception:
        logger.warning("hf_fallback_router: OpenAI client unavailable")
        return fallback

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    try:
        resp = client.chat.completions.create(
            model=router_model.strip(),
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.45,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.info("hf_fallback_router: router call failed: %s", exc)
        return fallback

    picked = _parse_tier_model_json(content, tiers, flat)
    if picked:
        return picked
    for c in flat:
        if c in content:
            return c
    return fallback


_JSON_OBJ_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _parse_tier_model_json(
    content: str,
    tiers: List[Dict[str, Any]],
    flat: List[str],
) -> Optional[str]:
    if not content:
        return None
    blob = content
    m = _JSON_OBJ_RE.search(content)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    mid = data.get("model")
    if not isinstance(mid, str) or not mid.strip():
        return None
    mid = canonical_gemma_model_id(mid.strip())
    if mid not in flat:
        return None
    tier_i = data.get("tier")
    if isinstance(tier_i, int) and 0 <= tier_i < len(tiers):
        if mid in (tiers[tier_i].get("models") or []):
            return mid
    # Model valid globally — accept
    return mid


# Backwards-compat for tests / env-only lists (no tiers): comma-separated hub ids
_ENV_FLAT_CANDIDATES = "HERMES_HF_FALLBACK_CANDIDATES"


def resolve_hf_routed_model_flat_candidates(
    user_text: str,
    *,
    api_key: str,
    base_url: str,
    router_model: str,
    candidates: List[str],
) -> str:
    """Legacy path: single flat list (wraps as one tier)."""
    if not candidates:
        return router_model
    tiers = [{"id": "flat", "description": "", "models": list(candidates)}]
    return resolve_hf_routed_model(
        user_text,
        api_key=api_key,
        base_url=base_url,
        router_model=router_model,
        tiers=tiers,
    )


def env_flat_candidates() -> List[str]:
    raw = os.environ.get(_ENV_FLAT_CANDIDATES, "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]
