"""Collect models from ``free_model_routing`` + primary model for CLI ``/models``."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.free_model_routing import normalize_kimi_tiers
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
        rm = _strip(kr.get("router_model"))
        if rm:
            _add_hf(rm, "free_model_routing.kimi_router (router)")

        tiers = normalize_kimi_tiers(kr.get("tiers"))
        hub_filter = bool(fmr.get("filter_free_tier_models_by_local_hub", True))
        for tier in tiers:
            tid = _strip(tier.get("id")) or "tier"
            desc = _strip(tier.get("description"))
            label = f"routing tier {tid}"
            if desc:
                label = f"{label}: {desc}"
            raw_models = [ _strip(x) for x in (tier.get("models") or []) if _strip(x) ]
            for mid in filter_hub_model_ids_by_local_state(raw_models, enabled=hub_filter):
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
