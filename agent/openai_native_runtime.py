"""Resolve api.openai.com chat base URL + API key for native OpenAI (non-OpenRouter).

**Keys (priority):** ``OPENAI_API_KEY_DROPLET`` first (VPS / split-env), then
``OPENAI_API_KEY``. This avoids mixing a workstation OpenAI key with droplet-only
credentials when both are set.

**Base URL:** ``OPENAI_BASE_URL`` (optional); default ``https://api.openai.com/v1``.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

DEFAULT_OPENAI_CHAT_BASE = "https://api.openai.com/v1"

# Tier E/F consultants: always hit api.openai.com when a native key exists (not OpenRouter),
# unless the user explicitly routes via OpenRouter (e.g. /models OpenRouter shortcut).
_NATIVE_CONSULTANT_CORE = frozenset({"gpt-5.4", "gpt-5.3-codex"})


def native_openai_api_key() -> str:
    """Prefer droplet key, then standard ``OPENAI_API_KEY``."""
    return (
        os.getenv("OPENAI_API_KEY_DROPLET", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def resolve_native_openai_chat_base_url() -> str:
    bu = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    if not bu:
        return DEFAULT_OPENAI_CHAT_BASE
    low = bu.lower()
    if "api.openai.com" in low and not low.endswith("/v1"):
        return bu + "/v1"
    return bu


def native_openai_runtime_tuple() -> Optional[Tuple[str, str]]:
    """Return ``(base_url, api_key)`` or ``None`` when no native OpenAI key is set."""
    ak = native_openai_api_key()
    if not ak:
        return None
    return resolve_native_openai_chat_base_url(), ak


def _core_model_id(model_id: str) -> str:
    m = (model_id or "").strip().lower()
    if m.startswith("openai/"):
        return m[7:]
    return m


def is_native_openai_consultant_model_id(model_id: str) -> bool:
    """True for tier E/F GPT-5 consultants (bare or ``openai/`` slug)."""
    return _core_model_id(model_id) in _NATIVE_CONSULTANT_CORE


def bare_openai_api_model_id(model_id: str) -> Optional[str]:
    """Return bare OpenAI API model id (``gpt-5.4`` / ``gpt-5.3-codex``) or None."""
    if not is_native_openai_consultant_model_id(model_id):
        return None
    return _core_model_id(model_id)
