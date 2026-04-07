"""Substrings removed from tier routing, /models menus, and OpenRouter pickers."""

from __future__ import annotations

from typing import Iterable, List, Sequence

# User-requested exclusions (case-insensitive substring match on model id).
_ROUTING_BLOCKLIST_SUBSTRINGS: tuple[str, ...] = (
    "kimi",
    "minimax",
    "gemma-3",
    "deepseek",
    "gpt-oss",
)

_DEFAULT_REPLACEMENT = "openrouter/auto"


def is_routing_blocklisted(model_id: str) -> bool:
    s = (model_id or "").lower()
    return any(b in s for b in _ROUTING_BLOCKLIST_SUBSTRINGS)


def replace_if_blocklisted(model_id: str, replacement: str = _DEFAULT_REPLACEMENT) -> str:
    mid = (model_id or "").strip()
    if not mid:
        return mid
    return replacement if is_routing_blocklisted(mid) else mid


def filter_blocklisted_models(ids: Sequence[str]) -> List[str]:
    return [m for m in ids if m and not is_routing_blocklisted(m)]
