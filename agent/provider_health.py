"""Session-scoped provider health tracking and blacklisting.

Tracks consecutive API failures per provider and blacklists providers that
exceed a configurable failure threshold for the remainder of the session.
HuggingFace is blacklisted after a single failure (credits deplete often).

Reset on new session or manual ``/model`` switch.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

_DEFAULT_MAX_FAILURES = 3
_HUGGINGFACE_MAX_FAILURES = 1


class ProviderHealthTracker:
    """Session-scoped provider error tracker with automatic blacklisting."""

    def __init__(
        self,
        *,
        default_max_failures: int = _DEFAULT_MAX_FAILURES,
        huggingface_max_failures: int = _HUGGINGFACE_MAX_FAILURES,
        overrides: Optional[Dict[str, int]] = None,
    ):
        self._failures: Dict[str, int] = {}
        self._blacklisted: Set[str] = set()
        self._blacklist_reasons: Dict[str, str] = {}
        self._default_max = max(default_max_failures, 1)
        self._provider_max: Dict[str, int] = {
            "huggingface": max(huggingface_max_failures, 1),
        }
        if overrides:
            for k, v in overrides.items():
                self._provider_max[k.lower().strip()] = max(int(v), 1)

    def _max_for(self, provider: str) -> int:
        return self._provider_max.get(provider, self._default_max)

    def record_failure(self, provider: str, error_hint: str = "") -> bool:
        """Record a failure for *provider*. Returns True if now blacklisted."""
        p = (provider or "").strip().lower()
        if not p or p in self._blacklisted:
            return p in self._blacklisted
        self._failures[p] = self._failures.get(p, 0) + 1
        mx = self._max_for(p)
        if self._failures[p] >= mx:
            self._blacklisted.add(p)
            reason = f"{self._failures[p]} consecutive failures"
            if error_hint:
                reason = f"{reason} ({error_hint[:80]})"
            self._blacklist_reasons[p] = reason
            logger.warning(
                "provider_health: blacklisted %s for session (%s)", p, reason,
            )
            return True
        return False

    def record_success(self, provider: str) -> None:
        """Reset failure count on successful API call."""
        p = (provider or "").strip().lower()
        if p and p in self._failures and p not in self._blacklisted:
            self._failures[p] = 0

    def is_blacklisted(self, provider: str) -> bool:
        return (provider or "").strip().lower() in self._blacklisted

    def blacklist_reason(self, provider: str) -> str:
        return self._blacklist_reasons.get(
            (provider or "").strip().lower(), ""
        )

    def reset(self) -> None:
        """Full reset (new session)."""
        self._failures.clear()
        self._blacklisted.clear()
        self._blacklist_reasons.clear()

    def summary(self) -> Dict[str, Any]:
        return {
            "failures": dict(self._failures),
            "blacklisted": sorted(self._blacklisted),
        }
