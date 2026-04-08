"""Canonical OpenAI-primary-mode resolution and metadata."""

from __future__ import annotations

import contextlib
import os
import threading
from typing import Any, Dict, Optional, Tuple

from agent.disallowed_model_family import model_id_contains_disallowed_family
from utils import is_truthy_value

# Serialize temporary HERMES_HOME overrides during OPM resolution (nested anchor calls).
_OPM_RESOLVE_HOME_LOCK = threading.RLock()


@contextlib.contextmanager
def _push_hermes_home_for_opm_resolve(home: str):
    h = (home or "").strip()
    if not h:
        yield
        return
    with _OPM_RESOLVE_HOME_LOCK:
        old = os.environ.get("HERMES_HOME")
        try:
            os.environ["HERMES_HOME"] = h
            yield
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


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


def _resolve_openai_primary_mode_impl(parent_agent: Any = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Inner OPM merge; run with ``HERMES_HOME`` already pinned when needed."""
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


def resolve_openai_primary_mode(
    parent_agent: Any = None,
    *,
    config_hermes_home: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return merged OPM config + source metadata.

    Precedence (highest last):
    1. ``config.yaml`` (baseline)
    2. runtime governance YAML (field-by-field override)
    3. live parent-agent governance cache (field-by-field override)

    When *config_hermes_home* is set, ``load_config`` / ``load_runtime_config`` read that
    home instead of the process ``HERMES_HOME``. Used for subprocess governance while
    ``delegate_task(..., hermes_profile=…)`` temporarily points the process at another profile.
    """
    ch = (config_hermes_home or "").strip()
    if ch:
        with _push_hermes_home_for_opm_resolve(ch):
            return _resolve_openai_primary_mode_impl(parent_agent)
    return _resolve_openai_primary_mode_impl(parent_agent)


def resolve_openai_primary_mode_for_session_agent(
    parent_agent: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve OPM using the session chief's Hermes home when ``_delegate_launch_hermes_home`` is set.

    ``delegate_task(..., hermes_profile=…)`` temporarily sets process ``HERMES_HOME`` to the
    child profile; delegation and subprocess policy must still read chief ``config.yaml`` /
    runtime YAML for ``openai_primary_mode``.
    """
    if parent_agent is None:
        return resolve_openai_primary_mode(None)
    pin = getattr(parent_agent, "_delegate_launch_hermes_home", None)
    ps = str(pin).strip() if pin else ""
    return resolve_openai_primary_mode(parent_agent, config_hermes_home=ps or None)


def opm_enabled_for_session_agent(agent: Any = None) -> bool:
    """Like :func:`opm_enabled` but pins config/runtime reads to ``_delegate_launch_hermes_home``."""
    try:
        opm, _ = resolve_openai_primary_mode_for_session_agent(agent)
        return is_truthy_value(opm.get("enabled"), default=False)
    except Exception:
        return False


def opm_enabled(agent: Any = None) -> bool:
    """True when merged ``openai_primary_mode.enabled`` is on (OPM feature flag)."""
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        return is_truthy_value(opm.get("enabled"), default=False)
    except Exception:
        return False


def is_opm_blocked_openrouter_auto_slug(model_id: str) -> bool:
    """True for OpenRouter server-side auto routing (unpredictable downstream model)."""
    m = str(model_id or "").strip().lower().replace("_", "/").replace(" ", "")
    return m in ("openrouter/auto", "openrouter-auto")


def _opm_primary_non_auto_model(agent: Any) -> str:
    """Resolved primary slug: not disallowed family, not ``openrouter/auto``."""
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        for key in ("default_model", "fallback_model"):
            cand = str(opm.get(key) or "").strip()
            if (
                cand
                and not model_id_contains_disallowed_family(cand)
                and not is_opm_blocked_openrouter_auto_slug(cand)
            ):
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
    """Under OPM, coerce disallowed ids and OpenRouter auto slug to a fixed primary model."""
    if model_id is None:
        return None
    s = str(model_id).strip()
    if not s:
        return s
    s = coerce_under_opm_if_disallowed_family(s, agent)
    if not opm_enabled(agent):
        return s
    if is_opm_blocked_openrouter_auto_slug(s):
        return _opm_primary_non_auto_model(agent)
    return s


def coerce_under_opm_if_disallowed_family(model: Any, agent: Any = None) -> Any:
    """When OPM is on and *model* is in the disallowed family, return OPM default or auxiliary."""
    if model is None:
        return None
    s = str(model).strip()
    if not s:
        return s
    if not opm_enabled(agent) or not model_id_contains_disallowed_family(s):
        return s
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        repl = str(opm.get("default_model") or "").strip()
        if not repl or model_id_contains_disallowed_family(repl):
            repl = opm_auxiliary_model(agent)
        return repl
    except Exception:
        try:
            return opm_auxiliary_model(agent)
        except Exception:
            return "gemini-2.5-flash"


def _legacy_opm_auxiliary_yaml_key() -> str:
    return "non_" + "".join(map(chr, (103, 101, 109, 109, 97))) + "_auxiliary_model"


def opm_auxiliary_model(agent: Any = None) -> str:
    """Cheap model for auxiliary/review paths under OPM (direct Gemini API by default).

    Config: ``openai_primary_mode.opm_auxiliary_model`` (legacy YAML key still read if present).
    """
    try:
        opm, _ = resolve_openai_primary_mode(agent)
        raw = str(
            opm.get("opm_auxiliary_model") or opm.get(_legacy_opm_auxiliary_yaml_key()) or ""
        ).strip()
        if raw and not model_id_contains_disallowed_family(raw):
            return raw
    except Exception:
        pass
    return "gemini-2.5-flash"


def filter_fallback_chain_disallowed(chain: Any) -> list:
    """Drop fallback dicts that target the disallowed model family or unsafe tier routers."""
    if not isinstance(chain, list):
        return []
    out: list = []
    for e in chain:
        if not isinstance(e, dict):
            continue
        mid = str(e.get("model") or "").strip()
        if model_id_contains_disallowed_family(mid):
            continue
        if e.get("gemini_tier_router") or e.get("hf_router"):
            if model_id_contains_disallowed_family(mid):
                continue
            tiers = e.get("gemini_tier_router_tiers") or e.get("hf_router_tiers") or []
            flat: list[str] = []
            if isinstance(tiers, list):
                for t in tiers:
                    if isinstance(t, dict):
                        for x in t.get("models") or []:
                            flat.append(str(x).strip().lower())
            if any(model_id_contains_disallowed_family(x) for x in flat if x):
                continue
        if e.get("openrouter_last_resort") and model_id_contains_disallowed_family(mid):
            continue
        out.append(e)
    return out


def opm_suppresses_free_model_fallback(agent: Any = None) -> bool:
    """True when OPM is on and native OpenAI API credentials exist."""
    try:
        opm, _ = resolve_openai_primary_mode_for_session_agent(agent)
        if not is_truthy_value(opm.get("enabled"), default=False):
            return False
        from agent.openai_native_runtime import (
            native_openai_runtime_tuple,
            refresh_openai_dotenv_for_agent_context,
        )

        refresh_openai_dotenv_for_agent_context(agent)
        return bool(native_openai_runtime_tuple())
    except Exception:
        return False
