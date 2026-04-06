"""Kimi tier routing on the Hugging Face hub OpenAI-compatible API (router.huggingface.co).

Model IDs come from configuration (``free_model_routing`` / ``fallback_providers``).

Set ``HERMES_HF_ROUTER_DISABLE=1`` to skip the Kimi tiered router and use that
entry's ``model`` field as-is.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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


def first_tier_hub_fallback(tiers: List[Dict[str, Any]], router_model: str) -> str:
    """First hub id in tier order; else *router_model*."""
    flat = _flatten_tier_models(tiers)
    return flat[0] if flat else router_model


def resolve_gemini_routed_model(
    user_text: str,
    *,
    router_model: str,
    tiers: List[Dict[str, Any]],
) -> str:
    """Pick one hub id from *tiers* using Google AI (Gemini / Gemma API) *router_model*.

    Uses ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``. Same JSON shape as the HF router path.
    """
    if os.environ.get("HERMES_HF_ROUTER_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return first_tier_hub_fallback(tiers, router_model)

    if not tiers:
        return router_model

    flat = _flatten_tier_models(tiers)
    fallback = first_tier_hub_fallback(tiers, router_model)
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
        return fallback

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
        return fallback

    picked = _parse_tier_model_json(content, tiers, flat)
    if picked:
        return picked
    for c in flat:
        if c in content:
            return c
    return fallback


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
    mid = mid.strip()
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
