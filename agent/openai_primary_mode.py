"""Canonical OpenAI-primary-mode resolution and metadata."""

from __future__ import annotations

from typing import Any, Dict, Tuple


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

    source = "none"
    if parent_opm:
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
        "enabled": bool(merged.get("enabled", False)),
        "source": source,
        "has_runtime_yaml": bool(rt_opm),
        "has_config_yaml": bool(cfg_opm),
        "has_parent_cached": bool(parent_opm),
        "has_native_openai_runtime": has_native_openai_runtime,
        "require_direct_openai": bool(merged.get("require_direct_openai", True)),
    }
    return merged, meta


def opm_suppresses_free_model_fallback(agent: Any = None) -> bool:
    """True when OpenAI-primary mode is on and native OpenAI API credentials exist.

    Single gate for: no Gemma/Gemini fallback chain, no smart cheap-route downgrades,
    tier picks forced to GPT, delegation baseline forced to native OpenAI.

    Pass *agent* so parent's ``_token_governance_cfg`` merges into OPM resolution
    (same as :func:`resolve_openai_primary_mode`).
    """
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        if not opm.get("enabled"):
            return False
        from agent.openai_native_runtime import native_openai_runtime_tuple

        return bool(native_openai_runtime_tuple())
    except Exception:
        return False

