"""Collect models from ``free_model_routing`` + primary model for CLI ``/models``."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.free_model_routing import (
    gemini_native_tier_model_set,
    normalize_kimi_tiers,
    raw_free_model_routing_tiers,
)
from agent.local_inference import filter_hub_model_ids_by_local_state


def _strip(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def collect_pipeline_models(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return menu rows for ``/models``: ``model``, ``source``, ``provider_kind``.

    *provider_kind* is ``primary`` (current profile primary), ``huggingface``, or ``gemini``.
    Order: primary, then tier router → tier hub models (deduped), then optional Gemini.
    """
    if not config or not isinstance(config, dict):
        return []

    out: List[Dict[str, Any]] = []
    seen_hf: set[str] = set()
    seen_gemini: set[str] = set()

    def _add_hf(model_id: str, source: str) -> None:
        mid = _strip(model_id)
        if not mid or mid in seen_hf:
            return
        seen_hf.add(mid)
        out.append({"model": mid, "source": source, "provider_kind": "huggingface"})

    def _add_gemini(model_id: str, source: str) -> None:
        mid = _strip(model_id)
        if not mid or mid in seen_gemini:
            return
        seen_gemini.add(mid)
        out.append({"model": mid, "source": source, "provider_kind": "gemini"})

    mc = config.get("model")
    if isinstance(mc, dict):
        primary = _strip(mc.get("default") or mc.get("model"))
    else:
        primary = _strip(mc)
    if primary:
        out.append(
            {
                "model": primary,
                "source": "primary (config model.default)",
                "provider_kind": "primary",
            }
        )

    fmr = config.get("free_model_routing")
    if not isinstance(fmr, dict) or not fmr.get("enabled"):
        return out

    kr = fmr.get("kimi_router") or {}
    if isinstance(kr, dict):
        f_native = gemini_native_tier_model_set(fmr)
        rm = _strip(kr.get("router_model"))
        if rm:
            if rm in f_native:
                _add_gemini(rm, "free_model_routing.kimi_router (router)")
            else:
                _add_hf(rm, "free_model_routing.kimi_router (router)")

        tiers = normalize_kimi_tiers(raw_free_model_routing_tiers(fmr))
        hub_filter = bool(fmr.get("filter_free_tier_models_by_local_hub", True))
        for tier in tiers:
            tid = _strip(tier.get("id")) or "tier"
            desc = _strip(tier.get("description"))
            label = f"routing tier {tid}"
            if desc:
                label = f"{label}: {desc}"
            raw_models = [_strip(x) for x in (tier.get("models") or []) if _strip(x)]
            hub_only = [m for m in raw_models if m not in f_native]
            filtered_hub = filter_hub_model_ids_by_local_state(hub_only, enabled=hub_filter)
            for mid in raw_models:
                if mid in f_native:
                    _add_gemini(mid, label)
                elif mid in filtered_hub:
                    _add_hf(mid, label)

    og = fmr.get("optional_gemini") or {}
    if isinstance(og, dict) and og.get("enabled"):
        gm = _strip(og.get("model"))
        if gm and gm not in seen_gemini:
            seen_gemini.add(gm)
            out.append(
                {
                    "model": gm,
                    "source": "free_model_routing.optional_gemini (Gemini API)",
                    "provider_kind": "gemini",
                }
            )

    return out
