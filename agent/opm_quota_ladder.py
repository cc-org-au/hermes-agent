"""OPM native OpenAI quota downgrade ladder (routing_canon ``opm_native_quota_downgrade``).

When OpenAI-primary mode is active and api.openai.com hits quota/rate limits, step down
through configured model lists *before* activating cross-provider fallback. Per turn,
tier routing still picks the top model first; ladder only applies within a single
``run_conversation`` retry loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils import is_truthy_value

logger = logging.getLogger(__name__)


def _bare_slug(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()
    if low.startswith("openai/"):
        return m[7:].strip()
    return m


# Legacy / mistaken canon overlays used bare ``gpt-5.3``; OpenAI returns 400 model_not_found.
# Map to a real Chat Completions id (same tier intent: cheaper than gpt-5.4 flagship).
_OPM_NATIVE_LADDER_MODEL_ALIASES = {
    "gpt-5.3": "gpt-5.4-mini",
}


def _canonical_ladder_id(bare: str) -> str:
    key = (bare or "").strip().lower()
    return _OPM_NATIVE_LADDER_MODEL_ALIASES.get(key, bare)


def _normalize_ladder(entries: Any) -> List[str]:
    if not isinstance(entries, list):
        return []
    out: List[str] = []
    for x in entries:
        s = _canonical_ladder_id(_bare_slug(str(x).strip()))
        if s and s not in out:
            out.append(s)
    return out


def load_opm_native_quota_downgrade_config() -> Dict[str, Any]:
    """Return merged canon block with normalized lists and a precomputed id set."""
    from agent.routing_canon import load_merged_routing_canon

    canon = load_merged_routing_canon()
    raw = canon.get("opm_native_quota_downgrade")
    if not isinstance(raw, dict):
        raw = {}
    enabled = is_truthy_value(raw.get("enabled"), default=True)
    chat = _normalize_ladder(raw.get("chat_models"))
    codex = _normalize_ladder(raw.get("codex_models"))
    ladder_set = frozenset(chat) | frozenset(codex)
    return {
        "enabled": enabled,
        "chat_models": chat,
        "codex_models": codex,
        "ladder_model_set": ladder_set,
    }


def opm_quota_ladder_subprocess_core_ids() -> frozenset[str]:
    """Bare model ids in ``chat_models`` ∪ ``codex_models`` when the ladder is enabled."""
    try:
        cfg = load_opm_native_quota_downgrade_config()
        if not cfg.get("enabled"):
            return frozenset()
        ls = cfg.get("ladder_model_set") or frozenset()
        return ls if isinstance(ls, frozenset) else frozenset(ls)
    except Exception:
        logger.debug("opm_quota_ladder_subprocess_core_ids failed", exc_info=True)
        return frozenset()


def opm_native_ladder_model_uses_openai_tuple(agent: Any, model_id: str) -> bool:
    """True when *model_id* is listed in the quota ladder and OPM + ladder are enabled."""
    try:
        from agent.openai_primary_mode import opm_enabled

        cfg = load_opm_native_quota_downgrade_config()
        if not cfg.get("enabled") or not ladder_model_set_non_empty(cfg):
            return False
        if not opm_enabled(agent):
            return False
        bare = _bare_slug(model_id).lower()
        return bare in {x.lower() for x in cfg["ladder_model_set"]}
    except Exception:
        logger.debug("opm_native_ladder_model_uses_openai_tuple failed", exc_info=True)
        return False


def ladder_model_set_non_empty(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("ladder_model_set"))


def cheapest_opm_native_chat_slug() -> Optional[str]:
    """Smallest chat rung from ``opm_native_quota_downgrade.chat_models`` (for trivial OPM clamps).

    Picks the first match in cost-preference order (nano → mini → 5.2), else the last
    ladder entry (canon lists are typically flagship-first).
    """
    cfg = load_opm_native_quota_downgrade_config()
    if not cfg.get("enabled") or not ladder_model_set_non_empty(cfg):
        return None
    chat = list(cfg.get("chat_models") or [])
    if not chat:
        return None
    bare_list = [_canonical_ladder_id(_bare_slug(str(x))) for x in chat]
    lower_map = {m.lower(): m for m in bare_list if m}
    for pref in ("gpt-5-nano", "gpt-4.1-nano", "gpt-5.4-nano", "gpt-5-mini", "gpt-5.4-mini", "gpt-5.2"):
        pl = pref.lower()
        if pl in lower_map:
            return lower_map[pl]
    return bare_list[-1]


def format_opm_native_slug_for_agent(agent: Any, bare_slug: str) -> str:
    """Bare api.openai.com id vs ``openai/…`` on OpenRouter — match tier routing conventions."""
    s = _canonical_ladder_id(_bare_slug(bare_slug))
    if not s:
        return bare_slug
    try:
        if getattr(agent, "_is_openrouter_url", lambda: False)():
            low = s.lower()
            if not low.startswith("openai/"):
                return f"openai/{_bare_slug(s)}"
    except Exception:
        logger.debug("format_opm_native_slug_for_agent openrouter check failed", exc_info=True)
    return s


def session_budget_next_cheaper_model(
    *,
    current_model: str,
    base_url: str,
    api_mode: str,
) -> Optional[str]:
    """Next cheaper slug from ``opm_native_quota_downgrade`` lists for session cost circuit.

    Used when session spend rate / budget trips the cost monitor: try a smaller ladder
    rung before or after ``fallback_providers``. Does **not** require OPM or a quota
    API error — only that the merged canon lists include the current model.

    OpenRouter ``openai/…`` slugs are preserved (``gpt-5.4`` → ``openai/gpt-5.4-mini``).
    """
    cfg = load_opm_native_quota_downgrade_config()
    if not cfg.get("enabled") or not ladder_model_set_non_empty(cfg):
        return None
    nxt = next_quota_downgrade_model(
        current_model=current_model,
        api_mode=api_mode,
        cfg=cfg,
    )
    if not nxt:
        return None
    low = (base_url or "").lower()
    cur_raw = (current_model or "").strip()
    if "openrouter" in low and cur_raw.lower().startswith("openai/"):
        bn = _bare_slug(nxt)
        if not bn.lower().startswith("openai/"):
            return f"openai/{bn}"
        return bn
    return nxt


def next_quota_downgrade_model(
    *,
    current_model: str,
    api_mode: str,
    cfg: Dict[str, Any],
) -> Optional[str]:
    """Return the next rung after *current_model*, or None.

    Native OpenAI often uses ``api_mode=codex_responses`` while the live slug is a
    chat-tier id (e.g. ``gpt-5.4``). We therefore resolve the current id against
    **both** ``chat_models`` and ``codex_models`` instead of choosing a single list
    from *api_mode* only.
    """
    del api_mode  # kept for API stability / callers; resolution is model-driven
    chat = list(cfg.get("chat_models") or [])
    codex = list(cfg.get("codex_models") or [])
    cur = _canonical_ladder_id(_bare_slug(current_model)).lower()

    def _idx_in(seq: List[str]) -> int:
        for i, m in enumerate(seq):
            slug = _canonical_ladder_id(_bare_slug(m)).lower()
            if slug == cur:
                return i
        return -1

    ic = _idx_in(chat)
    if ic >= 0 and ic + 1 < len(chat):
        return chat[ic + 1]
    ix = _idx_in(codex)
    if ix >= 0 and ix + 1 < len(codex):
        return codex[ix + 1]

    # Top chat slug on a codex HTTP stack (gpt-5.4 not listed under codex_models).
    if "codex" not in cur and chat:
        top = _canonical_ladder_id(_bare_slug(chat[0])).lower()
        if top == cur and len(chat) > 1:
            return chat[1]
    if "codex" in cur and codex:
        top = _canonical_ladder_id(_bare_slug(codex[0])).lower()
        if top == cur and len(codex) > 1:
            return codex[1]
    return None


def should_attempt_opm_native_downgrade(
    agent: Any,
    *,
    quota_style: bool,
    pool_may_recover: bool,
) -> Tuple[bool, Dict[str, Any]]:
    """Return (eligible, cfg) for trying a native ladder step on this error."""
    cfg = load_opm_native_quota_downgrade_config()
    if not cfg.get("enabled") or not ladder_model_set_non_empty(cfg):
        return False, cfg
    if not quota_style:
        return False, cfg
    if pool_may_recover:
        return False, cfg
    try:
        from agent.openai_primary_mode import opm_enabled, opm_manual_override_active

        if not opm_enabled(agent) or opm_manual_override_active(agent):
            return False, cfg
    except Exception:
        return False, cfg
    if getattr(agent, "_fallback_activated", False):
        return False, cfg
    # OpenRouter / cross-provider quota phase — native api.openai.com ladder does not apply.
    _qf = getattr(agent, "_opm_qf_phase", None) or "native"
    if _qf != "native":
        return False, cfg
    try:
        if not agent._is_direct_openai_url():
            return False, cfg
    except Exception:
        return False, cfg
    return True, cfg
