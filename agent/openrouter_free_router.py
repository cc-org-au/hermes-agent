"""Per-turn resolution for synthetic model id ``openrouter/free`` (OpenRouter free-tier only)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from hermes_constants import OPENROUTER_FREE_SYNTHETIC

logger = logging.getLogger(__name__)


class OpenRouterFreeResolutionError(Exception):
    """User-visible failure when no free-tier model is available."""


_cache_ids: Optional[List[str]] = None
_cache_exp: float = 0.0
_cache_ttl_used: int = 0


def clear_openrouter_free_cache_for_tests() -> None:
    global _cache_ids, _cache_exp, _cache_ttl_used
    _cache_ids = None
    _cache_exp = 0.0
    _cache_ttl_used = 0


def _model_row_is_free(row: dict) -> bool:
    mid = str(row.get("id") or "").strip()
    if mid.endswith(":free"):
        return True
    pr = row.get("pricing")
    if not isinstance(pr, dict):
        return False
    try:
        return float(pr.get("prompt", 1)) == 0.0 and float(pr.get("completion", 1)) == 0.0
    except (TypeError, ValueError):
        ps = str(pr.get("prompt", "1")).strip()
        cs = str(pr.get("completion", "1")).strip()
        return ps in {"0", "0.0", "0.00"} and cs in {"0", "0.0", "0.00"}


def fetch_openrouter_free_model_ids(
    api_key: str,
    base_url: str,
    *,
    timeout: float = 15.0,
) -> Optional[List[str]]:
    b = (base_url or "").rstrip("/")
    if not b or not (api_key or "").strip():
        return None
    url = b + "/models"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.debug("openrouter free fetch failed: %s", e)
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        return None
    out: List[str] = []
    for row in rows:
        if isinstance(row, dict) and row.get("id") and _model_row_is_free(row):
            out.append(str(row["id"]))
    return out


def get_openrouter_free_model_ids_cached(
    api_key: str,
    base_url: str,
    ttl_seconds: int,
    *,
    timeout: float = 15.0,
) -> Optional[List[str]]:
    global _cache_ids, _cache_exp, _cache_ttl_used
    now = time.monotonic()
    ttl = max(60, int(ttl_seconds))
    if _cache_ids is not None and now < _cache_exp and _cache_ttl_used == ttl:
        return list(_cache_ids)
    ids = fetch_openrouter_free_model_ids(api_key, base_url, timeout=timeout)
    if ids is None:
        return None
    _cache_ids = list(ids)
    _cache_exp = now + float(ttl)
    _cache_ttl_used = ttl
    return list(_cache_ids)


def pick_free_slug(
    candidate_slugs: List[str],
    live_free_ids: List[str],
    *,
    ranking: str,
    scores: Dict[str, int],
) -> Optional[str]:
    live = set(live_free_ids)
    eligible = [s for s in candidate_slugs if s in live]
    if not eligible:
        return None
    order = {s: i for i, s in enumerate(candidate_slugs)}
    if ranking.strip().lower() == "cheapest_first":
        return min(eligible, key=lambda s: order.get(s, 999))
    return sorted(
        eligible,
        key=lambda s: (-int(scores.get(s, 0)), order.get(s, 999)),
    )[0]


def resolve_openrouter_free_model_for_api(
    *,
    configured_model: str,
    api_key: str,
    base_url: str,
    timeout: float = 15.0,
) -> str:
    """Return model id for the OpenAI-compat ``model`` field.

    Default (``api_use_native_free_router``): return ``openrouter/free`` unchanged per OpenRouter
    Free Models Router (server-side capability + account data-policy filtering).

    Legacy: resolve to a concrete ``…:free`` slug from canon allowlist ∩ live ``GET /models``.
    """
    if (configured_model or "").strip() != OPENROUTER_FREE_SYNTHETIC:
        return configured_model

    from agent.routing_canon import load_openrouter_free_router_config

    cfg = load_openrouter_free_router_config()
    if not cfg.get("enabled", True):
        raise OpenRouterFreeResolutionError("openrouter/free router is disabled in routing canon.")

    if not (api_key or "").strip():
        raise OpenRouterFreeResolutionError(
            "openrouter/free requires OPENROUTER_API_KEY (or a configured API key)."
        )

    if cfg.get("api_use_native_free_router", True):
        return OPENROUTER_FREE_SYNTHETIC

    ttl = int(cfg.get("live_fetch_ttl_seconds") or 3600)
    live = get_openrouter_free_model_ids_cached(api_key, base_url, ttl, timeout=timeout)
    if live is None:
        raise OpenRouterFreeResolutionError(
            "openrouter/free: could not reach OpenRouter /models (network or auth)."
        )

    candidates = list(cfg.get("candidate_slugs") or [])
    chosen = pick_free_slug(
        candidates,
        live,
        ranking=str(cfg.get("ranking") or "capability_score"),
        scores=dict(cfg.get("capability_scores") or {}),
    )
    if not chosen:
        msg = str(cfg.get("empty_error_message") or "").strip() or (
            "openrouter/free: no free-tier model matched the routing canon allowlist."
        )
        raise OpenRouterFreeResolutionError(msg)
    return chosen
