"""Collect models from ``free_model_routing`` + primary model for CLI ``/models``."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.free_model_routing import (
    gemini_native_tier_model_set,
    normalize_kimi_tiers,
    raw_free_model_routing_tiers,
)
from agent.local_inference import filter_hub_model_ids_by_local_state
from agent.routing_model_blocklist import filter_blocklisted_models, is_routing_blocklisted

MENU_ACTION_OPENROUTER_BROWSE = "openrouter_browse"
MENU_ACTION_CHOOSE_ROUTER = "choose_router"

# Next-prompt routing: api.openai.com + OPENAI_API_KEY (bare model ids).
PROVIDER_KIND_OPENAI_NATIVE = "openai_native"
# Session router row: same stack, stored as custom+base_url on the agent override.
PROVIDER_KIND_OPENAI_NATIVE_ROUTER = "openai_native_router"


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
        if not mid or mid in seen_hf or is_routing_blocklisted(mid):
            return
        seen_hf.add(mid)
        out.append({"model": mid, "source": source, "provider_kind": "huggingface"})

    def _add_gemini(model_id: str, source: str) -> None:
        mid = _strip(model_id)
        if not mid or mid in seen_gemini or is_routing_blocklisted(mid):
            return
        seen_gemini.add(mid)
        out.append({"model": mid, "source": source, "provider_kind": "gemini"})

    mc = config.get("model")
    if isinstance(mc, dict):
        primary = _strip(mc.get("default") or mc.get("model"))
    else:
        primary = _strip(mc)
    if primary and not is_routing_blocklisted(primary):
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
        if rm and not is_routing_blocklisted(rm):
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
        if gm and gm not in seen_gemini and not is_routing_blocklisted(gm):
            seen_gemini.add(gm)
            out.append(
                {
                    "model": gm,
                    "source": "free_model_routing.optional_gemini (Gemini API)",
                    "provider_kind": "gemini",
                }
            )

    return out


def list_openrouter_picker_model_ids() -> List[str]:
    """Sorted OpenRouter slugs for full-model pickers (live API, else static catalog)."""
    try:
        from hermes_cli.models import fetch_openrouter_model_ids, model_ids

        live = fetch_openrouter_model_ids()
        base = live if live else model_ids()
    except Exception:
        from hermes_cli.models import model_ids

        base = model_ids()
    cleaned = filter_blocklisted_models(base)
    return sorted(set(cleaned), key=str.lower)


def collect_router_picker_model_rows() -> List[Dict[str, Any]]:
    """Flat rows for ``Choose-Router`` (native OpenAI pair first, then OpenRouter)."""
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for mid, src in (
        ("gpt-5.4", "native OpenAI (session router)"),
        ("gpt-5.3-codex", "native OpenAI (session router)"),
    ):
        seen.add(mid)
        rows.append(
            {
                "kind": "model",
                "model": mid,
                "source": src,
                "provider_kind": PROVIDER_KIND_OPENAI_NATIVE_ROUTER,
            }
        )
    for mid in list_openrouter_picker_model_ids():
        if mid in seen:
            continue
        seen.add(mid)
        rows.append(
            {
                "kind": "model",
                "model": mid,
                "source": "openrouter (session router)",
                "provider_kind": "openrouter",
            }
        )
    return rows


def collect_models_menu_entries(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows for interactive ``/models``: shortcuts, action rows, then pipeline models."""
    entries: List[Dict[str, Any]] = []

    def _add_shortcut(
        model: str,
        source: str,
        *,
        provider_kind: str = "openrouter",
    ) -> None:
        if is_routing_blocklisted(model):
            return
        entries.append(
            {
                "kind": "model",
                "model": model,
                "source": source,
                "provider_kind": provider_kind,
            }
        )

    _add_shortcut("gpt-5.4", "/models shortcut (native OpenAI)", provider_kind=PROVIDER_KIND_OPENAI_NATIVE)
    _add_shortcut(
        "gpt-5.3-codex",
        "/models shortcut (native OpenAI)",
        provider_kind=PROVIDER_KIND_OPENAI_NATIVE,
    )
    _add_shortcut("openai/gpt-5.4", "/models shortcut (OpenRouter)")
    _add_shortcut("openai/gpt-5.3-codex", "/models shortcut (OpenRouter)")
    _add_shortcut("openrouter/auto", "/models shortcut (OpenRouter auto)")

    entries.append(
        {
            "kind": "action",
            "action": MENU_ACTION_OPENROUTER_BROWSE,
            "label": "OpenRouter-(choose-model)…",
            "model": "",
            "source": "",
            "provider_kind": "action",
        }
    )
    entries.append(
        {
            "kind": "action",
            "action": MENU_ACTION_CHOOSE_ROUTER,
            "label": "Choose-Router…",
            "model": "",
            "source": "",
            "provider_kind": "action",
        }
    )

    for row in collect_pipeline_models(config):
        row = dict(row)
        row.setdefault("kind", "model")
        entries.append(row)

    return entries
