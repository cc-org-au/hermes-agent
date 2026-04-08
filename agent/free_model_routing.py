"""Build ``fallback_providers`` from ``free_model_routing`` in config.yaml.

Synthesized order:

1. **Gemini direct** — ``gemma-4-31b-it`` via Google AI (Gemini API).  The chain
   entry uses ``"provider": "gemini"`` directly — no HuggingFace inference hop.
   Tier ids that are blocklisted are excluded from routing and ``/models``.
   When every tier target is filtered out, ``fallback_free_routed_model``
   (default ``gemma-4-31b-it``) is used as the sole tier target.
2. **Optional Gemini** — last-resort hosted Gemma if ``optional_gemini`` is enabled.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.local_inference import filter_hub_model_ids_by_local_state
from agent.routing_model_blocklist import is_routing_blocklisted
from agent.tier_model_routing import canonical_gemma_model_id

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_NATIVE = frozenset({"gemma-4-31b-it"})
_DEFAULT_FALLBACK_FREE_ROUTED = "gemma-4-31b-it"


def raw_free_model_routing_tiers(fmr: Optional[Dict[str, Any]]) -> Any:
    """Return the raw ``tiers`` value: top-level ``free_model_routing.tiers`` wins over legacy ``kimi_router.tiers``."""
    if not isinstance(fmr, dict):
        return None
    if "tiers" in fmr:
        return fmr.get("tiers")
    kr = fmr.get("kimi_router")
    if isinstance(kr, dict):
        return kr.get("tiers")
    return None


def fallback_free_routed_model_id(fmr: Optional[Dict[str, Any]] = None) -> str:
    """Model id used alone when ``router_model`` is set but no tier targets remain after filtering."""
    if not isinstance(fmr, dict):
        return _DEFAULT_FALLBACK_FREE_ROUTED
    v = canonical_gemma_model_id(_strip(fmr.get("fallback_free_routed_model")))
    return v or _DEFAULT_FALLBACK_FREE_ROUTED


def gemini_native_tier_model_set(fmr: Optional[Dict[str, Any]] = None) -> frozenset[str]:
    """Tier model ids served via Gemini API, from config ``gemini_native_tier_models``."""
    if not isinstance(fmr, dict):
        return _DEFAULT_GEMINI_NATIVE
    raw = fmr.get("gemini_native_tier_models")
    if not isinstance(raw, list) or not raw:
        kr = fmr.get("kimi_router")
        if isinstance(kr, dict):
            raw = kr.get("gemini_native_tier_models")
    if isinstance(raw, list) and raw:
        return frozenset(
            canonical_gemma_model_id(str(x).strip()) for x in raw if str(x).strip()
        )
    return _DEFAULT_GEMINI_NATIVE


def _strip(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def normalize_kimi_tiers(raw: Any) -> List[Dict[str, Any]]:
    """Return ``[{"id": str, "description": str, "models": [str, ...]}, ...]``."""
    out: List[Dict[str, Any]] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        mids = raw.get("models")
        if isinstance(mids, list) and any(str(x).strip() for x in mids):
            out.append(
                {
                    "id": _strip(raw.get("id")) or "tier-0",
                    "description": _strip(raw.get("description")) or "",
                    "models": [
                        canonical_gemma_model_id(str(x).strip())
                        for x in mids
                        if str(x).strip()
                    ],
                }
            )
        return out
    if not isinstance(raw, list):
        return out
    for i, tier in enumerate(raw):
        if isinstance(tier, dict):
            mids = tier.get("models")
            if not isinstance(mids, list):
                continue
            models = [
                canonical_gemma_model_id(str(x).strip()) for x in mids if str(x).strip()
            ]
            if not models:
                continue
            out.append(
                {
                    "id": _strip(tier.get("id")) or f"tier-{i}",
                    "description": _strip(tier.get("description")),
                    "models": models,
                }
            )
        elif isinstance(tier, list):
            models = [
                canonical_gemma_model_id(str(x).strip()) for x in tier if str(x).strip()
            ]
            if models:
                out.append(
                    {
                        "id": f"tier-{i}",
                        "description": "",
                        "models": models,
                    }
                )
    return out


def _filtered_kimi_tiers(fmr: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply optional local-hub download filter to tier hub ids.

    ``gemini_native_tier_models`` (default ``gemma-4-31b-it``) are never stripped — they are
    served via Gemini API, not ``local_models/hub``.
    """
    tiers = normalize_kimi_tiers(raw_free_model_routing_tiers(fmr))
    hub_filter = bool(fmr.get("filter_free_tier_models_by_local_hub", True))
    native_set = gemini_native_tier_model_set(fmr)
    out: List[Dict[str, Any]] = []
    for t in tiers:
        if not isinstance(t, dict):
            continue
        mids = t.get("models") or []
        if not isinstance(mids, list):
            continue
        raw = [str(x).strip() for x in mids if str(x).strip()]
        hub_only = [m for m in raw if m not in native_set]
        filtered_hub = filter_hub_model_ids_by_local_state(hub_only, enabled=hub_filter)
        merged: List[str] = []
        for m in raw:
            if is_routing_blocklisted(m):
                continue
            if m in native_set:
                merged.append(m)
            elif m in filtered_hub:
                merged.append(m)
        if not merged:
            continue
        t2 = dict(t)
        t2["models"] = merged
        out.append(t2)
    return out


def build_free_fallback_chain(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return fallback chain dicts from ``free_model_routing`` (may be empty).

    Chain entries always use ``"provider": "gemini"`` — no HuggingFace inference hop.
    """
    if not config or not isinstance(config, dict):
        return []
    fmr = config.get("free_model_routing")
    if not isinstance(fmr, dict):
        return []
    if not fmr.get("enabled", False):
        return []

    chain: List[Dict[str, Any]] = []

    kr = fmr.get("kimi_router") or {}
    if isinstance(kr, dict):
        router_model = canonical_gemma_model_id(_strip(kr.get("router_model")))
        tiers = _filtered_kimi_tiers(fmr)
        if router_model and not tiers:
            fb = fallback_free_routed_model_id(fmr)
            tiers = normalize_kimi_tiers(
                [
                    {
                        "id": "fallback-free-routed",
                        "description": "Fallback when no free-routing tier targets remain after filtering",
                        "models": [fb],
                    }
                ]
            )
        if router_model and tiers:
            flat = [m for t in tiers for m in t.get("models", [])]
            if not flat:
                logger.warning("free_model_routing: tiers have no model ids — skipping tier router")
            else:
                chain.append(
                    {
                        "provider": "gemini",
                        "model": router_model,
                        "gemini_tier_router": True,
                        "gemini_tier_router_tiers": tiers,
                        "gemini_native_tier_models": sorted(gemini_native_tier_model_set(fmr)),
                    }
                )

    og = fmr.get("optional_gemini") or {}
    if isinstance(og, dict) and og.get("enabled") and _strip(og.get("model")):
        chain.append(
            {
                "provider": "gemini",
                "model": canonical_gemma_model_id(_strip(og.get("model"))),
                "only_rate_limit": bool(og.get("only_rate_limit", True)),
                "restore_health_check": bool(og.get("restore_health_check", True)),
            }
        )

    # Last resort: OpenRouter with gemma-4-31b-it, then any low-cost
    # alternative.  Only reached when ALL direct Gemini API entries above
    # have failed (errors, quota, unavailable).  OpenRouter is always paid
    # but is cheaper than most alternatives when using gemma.
    or_fallback = fmr.get("openrouter_last_resort", {})
    if isinstance(or_fallback, dict) and or_fallback.get("enabled", True):
        _or_model = canonical_gemma_model_id(
            _strip(or_fallback.get("model")) or "google/gemma-4-31b-it"
        )
        chain.append(
            {
                "provider": "openrouter",
                "model": _or_model,
                "only_rate_limit": True,
                "openrouter_last_resort": True,
            }
        )

    return chain


def _is_plain_hf_without_router(entry: Dict[str, Any]) -> bool:
    """Legacy Inference-Providers-style row: huggingface + hub id, no ``gemini_tier_router``."""
    if not isinstance(entry, dict):
        return False
    if str(entry.get("provider") or "").strip().lower() != "huggingface":
        return False
    if entry.get("gemini_tier_router") or entry.get("hf_router"):
        return False
    return bool(str(entry.get("model") or "").strip())


def _drop_plain_hf_without_router(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in entries if not _is_plain_hf_without_router(e)]


def resolve_fallback_providers(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve ``fallback_providers`` with ``free_model_routing`` when appropriate.

    - If ``fallback_providers`` is ``[]`` → no fallback (explicit opt-out).
    - Non-empty ``fallback_providers`` → legacy plain HF entries are dropped; tier routing
      entries only.  If nothing remains, use the synthesized chain.
    - Legacy ``fallback_model`` single dict: plain HF without router is ignored in favor of synthesis.
    - If ``fallback_providers`` is missing or ``None`` → build from ``free_model_routing``.
    """
    try:
        from agent.openai_primary_mode import opm_suppresses_free_model_fallback

        if opm_suppresses_free_model_fallback():
            return []
    except Exception:
        pass
    if not config or not isinstance(config, dict):
        return []
    synth = build_free_fallback_chain(config)
    fp = config.get("fallback_providers")
    if fp == []:
        return []
    if isinstance(fp, list) and len(fp) > 0:
        cleaned = [x for x in fp if isinstance(x, dict) and x.get("provider") and x.get("model")]
        cleaned = _drop_plain_hf_without_router(cleaned)
        if not cleaned:
            return synth
        return cleaned
    fm = config.get("fallback_model")
    if isinstance(fm, dict) and fm.get("provider") and fm.get("model"):
        if _is_plain_hf_without_router(fm):
            return synth
        return [fm]
    return synth
