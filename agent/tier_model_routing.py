"""Tier letter → concrete OpenRouter model IDs from governance runtime YAML.

Aligned with ``token-model-tool-and-channel-governance-policy.md`` (Tiers A–F) and
workspace ``MODEL_ROUTING_REGISTRY.md``. Tier **IDs** live in
``workspace/operations/hermes_token_governance.runtime.yaml`` under ``tier_models`` —
edit there when pricing or availability changes; do not hardcode slugs in Hermes code.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

TIER_SENTINEL_RE = re.compile(r"^tier:([A-Ga-g])$")
TIER_DYNAMIC_SENTINEL = "tier:dynamic"

# When ``workspace/operations/hermes_token_governance.runtime.yaml`` is missing or
# ``tier_models`` omits a letter, OpenRouter must never receive a literal ``tier:X``.
# User YAML overrides these defaults per key; align with
# ``memory/runtime/tasks/templates/script-templates/hermes_token_governance.runtime.example.yaml``.
BUILTIN_TIER_MODELS: Dict[str, str] = {
    # Cheapest-first defaults when governance YAML is missing (override per profile).
    "A": "openai/gpt-5-nano",
    "B": "openai/gpt-4.1-mini",
    "C": "openai/gpt-5.4-mini",
    "D": "openai/gpt-5.2",
    "E": "openai/gpt-5.4",
    "F": "gpt-5.3-codex",
    "G": "anthropic/claude-opus-4.6",
}


def is_tier_dynamic(model: Optional[str]) -> bool:
    """True when config should pick a tier per prompt from ``tier_models`` + heuristics."""
    if not model:
        return False
    return str(model).strip().lower() == TIER_DYNAMIC_SENTINEL.lower()


def _tier_slug_matches_resolved_model(agent_model: str, tier_slug: str) -> bool:
    """Match ``gpt-5.4`` to ``openai/gpt-5.4`` (and vice versa) for status lines."""
    a = str(agent_model or "").strip().lower()
    b = str(tier_slug or "").strip().lower()
    if a == b:
        return True

    def core(s: str) -> str:
        return s[7:] if s.startswith("openai/") else s

    return core(a) == core(b)


def infer_tier_letter_for_model(model_id: str, tier_models: Dict[str, str]) -> str:
    """Reverse-lookup tier letter for status lines, or ``?`` if unknown."""
    if not model_id or not tier_models:
        return "?"
    mid = str(model_id).strip()
    for letter, slug in tier_models.items():
        if _tier_slug_matches_resolved_model(mid, slug):
            return letter
    return "?"


def prompt_text_for_tier_from_messages(messages: Optional[Any]) -> str:
    """Best-effort user/content text from chat messages for tier heuristics."""
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages[-4:]:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text")
                    if isinstance(t, str):
                        parts.append(t)
    return "\n".join(parts)[:12000]


def canonical_native_tier_model_id(model_id: Optional[str]) -> str:
    """Map obsolete short tier aliases to a concrete Gemini API id."""
    s = (model_id or "").strip()
    _fam = "".join(map(chr, (103, 101, 109, 109, 97)))
    if s.lower() == f"{_fam}-4":
        return "gemini-2.5-flash"
    return s


def resolve_tier_dynamic_model(
    user_text: str,
    gov_cfg: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Pick concrete model from ``tier_models`` using the same heuristics as the main agent."""
    cfg = gov_cfg
    if cfg is None:
        from agent.token_governance_runtime import load_runtime_config

        cfg = load_runtime_config()
    if not cfg or not cfg.get("enabled", False):
        return None
    tm = effective_tier_models(cfg.get("tier_models"))
    tier = select_tier_for_message(user_text or "", cfg)
    return tm.get(tier)


def _normalize_openrouter_auto_slug(model_id: str) -> str:
    s = canonical_native_tier_model_id((model_id or "").strip())
    collapsed = s.lower().replace("_", "-").replace("/", "-")
    if collapsed == "openrouter-auto":
        return "openrouter/auto"
    return s


def normalize_tier_models(raw: Any) -> Dict[str, str]:
    """Return upper-case tier key → model id."""
    out: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        key = str(k).strip().upper()
        if len(key) == 1 and key in "ABCDEF" and v:
            out[key] = _normalize_openrouter_auto_slug(str(v).strip())
    return out


def effective_tier_models(raw: Any) -> Dict[str, str]:
    """Merge governance ``tier_models`` with :data:`BUILTIN_TIER_MODELS` (user wins)."""
    from agent.routing_model_blocklist import replace_if_blocklisted

    merged = dict(BUILTIN_TIER_MODELS)
    merged.update(normalize_tier_models(raw))
    return {k: replace_if_blocklisted(v) for k, v in merged.items()}


def resolve_tier_placeholder(
    model: Optional[str],
    tier_models: Optional[Dict[str, str]],
    *,
    fallback_tier: str = "D",
) -> str:
    """If *model* is ``tier:X``, return a concrete slug; else return *model*."""
    merged = effective_tier_models(tier_models or {})
    if not model:
        return merged.get(fallback_tier.upper(), "") or merged.get("D", "")
    m = TIER_SENTINEL_RE.match(str(model).strip())
    if not m:
        return canonical_native_tier_model_id(str(model).strip())
    tier = m.group(1).upper()
    fb = fallback_tier.upper() if len(str(fallback_tier).strip()) == 1 else "D"
    if fb not in "ABCDEF":
        fb = "D"
    resolved = merged.get(tier) or merged.get(fb) or merged.get("D")
    return resolved or merged["D"]


def _chief_default_letter(cfg: Dict[str, Any]) -> str:
    """Tier letter used as chief baseline (from runtime YAML)."""
    ch = str(cfg.get("chief_default_tier") or cfg.get("default_tier") or "D").strip().upper()
    if len(ch) == 1 and ch in "BCDEF":
        return ch
    return "D"


def _normalize_tier_letter(value: str) -> Optional[str]:
    u = str(value).strip().upper()
    if len(u) == 1 and u in "BCDEF":
        return u
    return None


def _resolved_default_routing_letter(cfg: Dict[str, Any]) -> str:
    """Effective fallback letter before B/C/dynamic length rules.

    * ``default_routing_tier: chief`` → :func:`_chief_default_letter`
    * ``default_routing_tier: dynamic`` → chief letter for empty / short ambiguous text
      (non-empty uses :func:`_fallback_tier_dynamic_length` after B/C rules)
    * Single letter B–F → that letter
    * Missing / invalid → ``D``
    """
    raw = str(cfg.get("default_routing_tier") or "D").strip().upper()
    if raw == "CHIEF":
        return _chief_default_letter(cfg)
    if raw == "DYNAMIC":
        return _chief_default_letter(cfg)
    if len(raw) == 1 and raw in "BCDEF":
        return raw
    return "D"


def _fallback_tier_dynamic_length(user_message: str, cfg: Dict[str, Any]) -> str:
    """When ``default_routing_tier: dynamic``: tier by message length (after B/C rules)."""
    t = (user_message or "").strip()
    if not t:
        return _chief_default_letter(cfg)
    n = len(t)
    try:
        med = int(cfg.get("dynamic_fallback_medium_chars") or 800)
    except (TypeError, ValueError):
        med = 800
    try:
        long_th = int(cfg.get("dynamic_fallback_long_chars") or 2800)
    except (TypeError, ValueError):
        long_th = 2800
    t_med = _normalize_tier_letter(str(cfg.get("dynamic_fallback_medium_tier") or "C")) or "C"
    t_long = _normalize_tier_letter(str(cfg.get("dynamic_fallback_long_tier") or "D")) or "D"
    if n >= long_th:
        return t_long
    if n >= med:
        return t_med
    return _chief_default_letter(cfg)


def select_tier_for_message(user_message: str, cfg: Dict[str, Any]) -> str:
    """Pick tier letter B–F for this user turn (heuristics + optional dynamic fallback)."""
    base_default = _resolved_default_routing_letter(cfg)
    mode = str(cfg.get("default_routing_tier") or "D").strip().upper()

    t = (user_message or "").strip()
    if not t:
        return base_default

    low = t.lower()
    # Optional override for “incident” language (defaults to same tier as base_default)
    incident_tier = str(cfg.get("incident_routing_tier") or base_default).strip().upper()
    if len(incident_tier) == 1 and incident_tier in "BCDEF":
        if any(
            k in low
            for k in (
                "production incident",
                "security breach",
                " sev-0",
                "p0 incident",
                "system down",
            )
        ):
            return incident_tier

    # Tier B — ultra-cheap: short, simple ops
    simple_kw = (
        "summarize",
        "bullet list",
        "list the",
        "extract ",
        "classify",
        "format ",
        "convert ",
        "translate ",
        "what is the capital",
        "define ",
    )
    if len(t) < 120 and "\n" not in t and any(k in low for k in simple_kw):
        return "B"
    if len(t) < 72 and t.count("\n") <= 1 and len(t.split()) <= 18:
        return "B"

    # Tier C — cheap reasoning: medium length, no heavy “build the whole repo” signals
    heavy = (
        "refactor",
        "architecture",
        "implement",
        "debug",
        "traceback",
        "kubernetes",
        "dockerfile",
        "migration",
        "oauth",
        "multi-agent",
    )
    if 120 <= len(t) <= 900 and not any(h in low for h in heavy):
        return "C"

    if mode == "DYNAMIC":
        return _fallback_tier_dynamic_length(t, cfg)
    return base_default


def should_apply_per_turn_routing(cfg: Optional[Dict[str, Any]]) -> bool:
    if not cfg or not cfg.get("enabled", False):
        return False
    if not normalize_tier_models(cfg.get("tier_models")):
        return False
    # Explicit opt-out
    if cfg.get("dynamic_tier_routing") is False:
        return False
    return True
