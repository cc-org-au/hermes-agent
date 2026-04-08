"""Canonical OpenAI-primary-mode resolution and metadata."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from utils import is_truthy_value


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dicts(_as_dict(out.get(key)), value)
        else:
            out[key] = value
    return out


def _opm_merge_parent_anchor(parent_agent: Any) -> Any:
    """Return ``parent_agent._opm_merge_parent`` when set, else None.

    ``unittest.mock.MagicMock`` implements ``__getattr__`` so
    ``getattr(mock, "_opm_merge_parent", None)`` yields a bogus child mock.
    Tests and callers without an anchor must see None so OPM resolution does not recurse.
    """
    if parent_agent is None:
        return None
    d = getattr(parent_agent, "__dict__", None)
    if isinstance(d, dict) and "_opm_merge_parent" in d:
        return d["_opm_merge_parent"]
    try:
        return object.__getattribute__(parent_agent, "_opm_merge_parent")
    except AttributeError:
        return None


def resolve_openai_primary_mode(parent_agent: Any = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return merged OPM config + source metadata.

    Precedence (highest last):
    1. ``config.yaml`` (baseline)
    2. runtime governance YAML (field-by-field override)
    3. live parent-agent governance cache (field-by-field override)
    """
    cfg_root: Dict[str, Any] = {}
    rt_root: Dict[str, Any] = {}
    parent_root: Dict[str, Any] = {}

    try:
        from hermes_cli.config import load_config

        cfg_root = _as_dict(load_config() or {})
    except Exception:
        cfg_root = {}

    try:
        from agent.token_governance_runtime import load_runtime_config

        rt_root = _as_dict(load_runtime_config() or {})
    except Exception:
        rt_root = {}

    if parent_agent is not None:
        parent_root = _as_dict(getattr(parent_agent, "_token_governance_cfg", None) or {})

    cfg_opm = _as_dict(cfg_root.get("openai_primary_mode"))
    rt_opm = _as_dict(rt_root.get("openai_primary_mode"))
    parent_opm = _as_dict(parent_root.get("openai_primary_mode"))

    merged = _merge_dicts(cfg_opm, rt_opm)
    merged = _merge_dicts(merged, parent_opm)

    # Delegated subagent under hermes_profile: child's config/YAML may omit OPM while
    # the chief has it enabled. Overlay the parent's merged OPM when the anchor is on.
    _anchor = _opm_merge_parent_anchor(parent_agent)
    _delegation_opm_overlay = False
    if _anchor is not None:
        anchor_merged, _ = resolve_openai_primary_mode(_anchor)
        if is_truthy_value(anchor_merged.get("enabled"), default=False):
            merged = _merge_dicts(merged, anchor_merged)
            _delegation_opm_overlay = True

    source = "none"
    if _delegation_opm_overlay:
        source = "delegation_parent"
    elif parent_opm:
        source = "parent_cached"
    elif rt_opm:
        source = "runtime_yaml"
    elif cfg_opm:
        source = "config_yaml"

    has_native_openai_runtime = False
    try:
        from agent.openai_native_runtime import native_openai_runtime_tuple

        has_native_openai_runtime = bool(native_openai_runtime_tuple())
    except Exception:
        has_native_openai_runtime = False

    meta = {
        "enabled": is_truthy_value(merged.get("enabled"), default=False),
        "source": source,
        "has_runtime_yaml": bool(rt_opm),
        "has_config_yaml": bool(cfg_opm),
        "has_parent_cached": bool(parent_opm),
        "has_native_openai_runtime": has_native_openai_runtime,
        "require_direct_openai": bool(merged.get("require_direct_openai", True)),
    }
    return merged, meta


def is_gemma_model_id(model_id: str) -> bool:
    """True for any Gemma-family id (never used when openai_primary_mode is enabled).

    Matches ``gemma-4-31b-it``, ``google/gemma-…``, hub ids containing ``gemma``, etc.
    """
    m = (model_id or "").strip().lower()
    return bool(m) and "gemma" in m


def opm_blocks_gemma(agent: Any = None) -> bool:
    """When OpenAI-primary mode is enabled (merged config), Gemma must never run."""
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        return is_truthy_value(opm.get("enabled"), default=False)
    except Exception:
        return False


def is_opm_blocked_openrouter_auto_slug(model_id: str) -> bool:
    """True for OpenRouter server-side auto routing (can pick Gemma though the request slug has no 'gemma')."""
    m = str(model_id or "").strip().lower().replace("_", "/").replace(" ", "")
    return m in ("openrouter/auto", "openrouter-auto")


def _opm_primary_non_auto_model(agent: Any) -> str:
    """Resolved primary slug: not Gemma, not ``openrouter/auto``; prefers OPM defaults then native OpenAI."""
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        for key in ("default_model", "fallback_model"):
            cand = str(opm.get(key) or "").strip()
            if cand and not is_gemma_model_id(cand) and not is_opm_blocked_openrouter_auto_slug(cand):
                return cand
    except Exception:
        pass
    try:
        from agent.openai_native_runtime import native_openai_api_key, native_openai_runtime_tuple

        rt = native_openai_runtime_tuple()
        if rt and rt[0] and native_openai_api_key():
            return "gpt-5.4"
    except Exception:
        pass
    return "gpt-5.4"


def coerce_opm_disallowed_routing_slugs(model_id: Any, agent: Any = None) -> Any:
    """Under OPM, coerce Gemma ids and OpenRouter auto-router slugs to a fixed primary model.

    ``openrouter/auto`` never contains the substring ``gemma`` but OpenRouter may still route
    to Gemma; treat it like Gemma for OPM hard-gate purposes.
    """
    if model_id is None:
        return None
    s = str(model_id).strip()
    if not s:
        return s
    s = coerce_model_off_gemma_under_opm(s, agent)
    if not opm_blocks_gemma(agent):
        return s
    if is_opm_blocked_openrouter_auto_slug(s):
        return _opm_primary_non_auto_model(agent)
    return s


def coerce_model_off_gemma_under_opm(model: Any, agent: Any = None) -> Any:
    """Return a non-Gemma model id when OPM is on and *model* is Gemma-family; else *model*.

    Single choke-point for hard-blocking Gemma at API boundaries. Prefer OPM
    ``default_model``; if missing or still Gemma, use :func:`opm_non_gemma_replacement_model`.
    """
    if model is None:
        return None
    s = str(model).strip()
    if not s:
        return s
    if not opm_blocks_gemma(agent) or not is_gemma_model_id(s):
        return s
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        repl = str(opm.get("default_model") or "").strip()
        if not repl or is_gemma_model_id(repl):
            repl = opm_non_gemma_replacement_model(agent)
        return repl
    except Exception:
        try:
            return opm_non_gemma_replacement_model(agent)
        except Exception:
            return "gemini-2.5-flash"


def opm_non_gemma_replacement_model(agent: Any = None) -> str:
    """Cheap non-Gemma id for auxiliary calls and last-resort fallbacks under OPM.

    Config override: ``openai_primary_mode.non_gemma_auxiliary_model`` (must not contain ``gemma``).
    Default: ``gemini-2.5-flash`` (direct Gemini API). OpenRouter-style
    ``google/gemini-…`` ids are normalized to bare ``gemini-…`` when using
    provider ``gemini`` (see ``normalize_gemini_api_model_id`` in
    ``agent/auxiliary_client.py``).
    """
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        raw = str(opm.get("non_gemma_auxiliary_model") or "").strip()
        if raw and not is_gemma_model_id(raw):
            return raw
    except Exception:
        pass
    return "gemini-2.5-flash"


def filter_fallback_chain_strip_gemma(chain: Any) -> list:
    """Drop fallback dicts that only exist to serve Gemma (model slug or tier router)."""
    if not isinstance(chain, list):
        return []
    out: list = []
    for e in chain:
        if not isinstance(e, dict):
            continue
        mid = str(e.get("model") or "").strip()
        if is_gemma_model_id(mid):
            continue
        if e.get("gemini_tier_router") or e.get("hf_router"):
            if is_gemma_model_id(mid):
                continue
            tiers = e.get("gemini_tier_router_tiers") or e.get("hf_router_tiers") or []
            flat: list[str] = []
            if isinstance(tiers, list):
                for t in tiers:
                    if isinstance(t, dict):
                        for x in t.get("models") or []:
                            flat.append(str(x).strip().lower())
            # Drop tier routers that can select Gemma for any tier target (strict OPM).
            if any(is_gemma_model_id(x) for x in flat if x):
                continue
        if e.get("openrouter_last_resort") and is_gemma_model_id(mid):
            continue
        out.append(e)
    return out


def opm_suppresses_free_model_fallback(agent: Any = None) -> bool:
    """True when OpenAI-primary mode is on and native OpenAI API credentials exist.

    Single gate for: no Gemma/Gemini fallback chain, no smart cheap-route downgrades,
    tier picks forced to GPT, delegation baseline forced to native OpenAI.

    Pass *agent* so parent's ``_token_governance_cfg`` merges into OPM resolution
    (same as :func:`resolve_openai_primary_mode`).
    """
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        if not is_truthy_value(opm.get("enabled"), default=False):
            return False
        from agent.openai_native_runtime import native_openai_runtime_tuple

        return bool(native_openai_runtime_tuple())
    except Exception:
        return False

