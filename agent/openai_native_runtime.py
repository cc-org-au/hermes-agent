"""Resolve api.openai.com chat base URL + API key for native OpenAI (non-OpenRouter)."""

from __future__ import annotations

import os
from typing import Optional, Tuple

DEFAULT_OPENAI_CHAT_BASE = "https://api.openai.com/v1"


def native_openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def resolve_native_openai_chat_base_url() -> str:
    bu = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    if not bu:
        return DEFAULT_OPENAI_CHAT_BASE
    low = bu.lower()
    if "api.openai.com" in low and not low.endswith("/v1"):
        return bu + "/v1"
    return bu


def native_openai_runtime_tuple() -> Optional[Tuple[str, str]]:
    """Return ``(base_url, api_key)`` or ``None`` when ``OPENAI_API_KEY`` is unset."""
    ak = native_openai_api_key()
    if not ak:
        return None
    return resolve_native_openai_chat_base_url(), ak
