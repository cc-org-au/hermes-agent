"""Build ``fallback_providers`` from ``free_model_routing`` in config.yaml.

Synthesized order (HF “Inference Providers” policy hop removed):

1. **Tiered router** — ``kimi_router.router_model`` picks one hub id from ``tiers``.
   Use ``router_provider: huggingface`` (default) with the HF router API, or
   ``router_provider: gemini`` with ``router_model: gemma-4-31b-it`` (Google AI) to choose among local checkpoints.
2. **Optional Gemini** — last-resort hosted Gemma if ``optional_gemini`` is enabled.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _strip(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def normalize_kimi_tiers(raw: Any) -> List[Dict[str, Any]]:
    """Return ``[{"id": str, "description": str, "models": [str, ...]}, ...]``."""
    out: List[Dict[str, Any]] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        # Single object with models — one tier
        mids = raw.get("models")
        if isinstance(mids, list) and any(str(x).strip() for x in mids):
            out.append(
                {
                    "id": _strip(raw.get("id")) or "tier-0",
                    "description": _strip(raw.get("description")) or "",
                    "models": [str(x).strip() for x in mids if str(x).strip()],
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
            models = [str(x).strip() for x in mids if str(x).strip()]
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
            models = [str(x).strip() for x in tier if str(x).strip()]
            if models:
                out.append(
                    {
                        "id": f"tier-{i}",
                        "description": "",
                        "models": models,
                    }
                )
    return out


def build_free_fallback_chain(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return fallback chain dicts from ``free_model_routing`` (may be empty)."""
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
        router_model = _strip(kr.get("router_model"))
        tiers = normalize_kimi_tiers(kr.get("tiers"))
        if router_model and tiers:
            flat = [m for t in tiers for m in t.get("models", [])]
            if not flat:
                logger.warning("free_model_routing.kimi_router: tiers have no model ids — skipping Kimi tier")
            else:
                rprov = _strip(kr.get("router_provider") or "huggingface").lower()
                if rprov not in ("huggingface", "gemini"):
                    logger.warning(
                        "free_model_routing.kimi_router: unknown router_provider %r — using huggingface",
                        rprov,
                    )
                    rprov = "huggingface"
                chain.append(
                    {
                        "provider": "huggingface",
                        "model": router_model,
                        "hf_router": True,
                        "hf_router_tiers": tiers,
                        "router_provider": rprov,
                    }
                )
        elif router_model and not tiers:
            logger.warning(
                "free_model_routing.kimi_router: router_model set but tiers empty — "
                "configure kimi_router.tiers for tiered routing",
            )

    og = fmr.get("optional_gemini") or {}
    if isinstance(og, dict) and og.get("enabled") and _strip(og.get("model")):
        chain.append(
            {
                "provider": "gemini",
                "model": _strip(og.get("model")),
                "only_rate_limit": bool(og.get("only_rate_limit", True)),
                "restore_health_check": bool(og.get("restore_health_check", True)),
            }
        )

    return chain


def _is_plain_hf_without_router(entry: Dict[str, Any]) -> bool:
    """Legacy Inference-Providers-style row: huggingface + hub id, no ``hf_router``."""
    if not isinstance(entry, dict):
        return False
    if str(entry.get("provider") or "").strip().lower() != "huggingface":
        return False
    if entry.get("hf_router"):
        return False
    return bool(str(entry.get("model") or "").strip())


def _drop_plain_hf_without_router(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in entries if not _is_plain_hf_without_router(e)]


def resolve_fallback_providers(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve ``fallback_providers`` with ``free_model_routing`` when appropriate.

    - If ``fallback_providers`` is ``[]`` → no fallback (explicit opt-out).
    - Non-empty ``fallback_providers`` → entries that look like legacy plain HF hub ids
      (no ``hf_router``) are **dropped**; Kimi routing uses ``hf_router`` rows only.
      If nothing remains, use the synthesized chain.
    - Legacy ``fallback_model`` single dict: plain HF without router is ignored in favor of synthesis.
    - If ``fallback_providers`` is missing or ``None`` → build from ``free_model_routing``.
    """
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
