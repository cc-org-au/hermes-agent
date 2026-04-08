"""Session-scoped cost monitoring with spike detection and circuit breaker.

Tracks cumulative session spend and rate of spend.  When the rate exceeds a
configurable threshold the monitor signals that the agent should hand over
context to a free model.

All state is session-scoped — no cross-session persistence.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_DAILY_BUDGET = 10.0
_DEFAULT_SESSION_BUDGET = 2.50
_DEFAULT_SPIKE_THRESHOLD_PER_MIN = 0.50
_RATE_WINDOW_SECONDS = 120.0  # sliding window for spend-rate calc


CostAction = Literal["ok", "warn", "circuit_break"]


class CostMonitor:
    """Lightweight spend-rate tracker with circuit-breaker semantics."""

    def __init__(
        self,
        *,
        daily_budget_usd: float = _DEFAULT_DAILY_BUDGET,
        session_budget_usd: float = _DEFAULT_SESSION_BUDGET,
        spike_threshold_usd_per_min: float = _DEFAULT_SPIKE_THRESHOLD_PER_MIN,
    ):
        self.daily_budget_usd = max(daily_budget_usd, 0.01)
        self.session_budget_usd = max(session_budget_usd, 0.01)
        self.spike_threshold_usd_per_min = max(spike_threshold_usd_per_min, 0.01)

        self._samples: List[Tuple[float, float]] = []  # (monotonic_time, cumulative_usd)
        self._circuit_broken = False
        self._warned_80 = False

    # ------------------------------------------------------------------
    def record_cost(self, cumulative_usd: float) -> CostAction:
        """Record cumulative session cost after an API call.

        Returns ``'ok'``, ``'warn'`` (80 % budget), or ``'circuit_break'``
        (spike or budget exceeded).
        """
        now = time.monotonic()
        self._samples.append((now, cumulative_usd))
        self._prune_old_samples(now)

        if cumulative_usd >= self.session_budget_usd:
            self._circuit_broken = True
            logger.warning(
                "cost_monitor: session budget exceeded ($%.2f / $%.2f)",
                cumulative_usd, self.session_budget_usd,
            )
            return "circuit_break"

        rate = self._spend_rate_per_min()
        if rate is not None and rate >= self.spike_threshold_usd_per_min:
            self._circuit_broken = True
            logger.warning(
                "cost_monitor: spend rate $%.3f/min exceeds threshold $%.2f/min",
                rate, self.spike_threshold_usd_per_min,
            )
            return "circuit_break"

        if not self._warned_80 and cumulative_usd >= self.session_budget_usd * 0.8:
            self._warned_80 = True
            return "warn"

        return "ok"

    # ------------------------------------------------------------------
    def should_force_free_model(self) -> bool:
        return self._circuit_broken

    def spend_rate_per_min(self) -> Optional[float]:
        """Current spend rate in $/min (None if insufficient data)."""
        return self._spend_rate_per_min()

    def status_line(self, cumulative_usd: float) -> str:
        rate = self._spend_rate_per_min()
        rate_s = f"${rate:.3f}/min" if rate is not None else "n/a"
        return (
            f"[Cost] ${cumulative_usd:.3f} / ${self.session_budget_usd:.2f} "
            f"(rate {rate_s})"
        )

    def reset(self) -> None:
        self._samples.clear()
        self._circuit_broken = False
        self._warned_80 = False

    # ------------------------------------------------------------------
    def _prune_old_samples(self, now: float) -> None:
        cutoff = now - _RATE_WINDOW_SECONDS
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    def _spend_rate_per_min(self) -> Optional[float]:
        if len(self._samples) < 2:
            return None
        oldest_t, oldest_c = self._samples[0]
        newest_t, newest_c = self._samples[-1]
        dt = newest_t - oldest_t
        if dt < 5.0:  # need at least 5 s of data
            return None
        delta_cost = newest_c - oldest_c
        return max(delta_cost / (dt / 60.0), 0.0)


def load_cost_governance_config(gov_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Extract cost_governance values from token governance runtime config."""
    defaults = {
        "daily_budget_usd": _DEFAULT_DAILY_BUDGET,
        "session_budget_usd": _DEFAULT_SESSION_BUDGET,
        "spike_threshold_usd_per_min": _DEFAULT_SPIKE_THRESHOLD_PER_MIN,
    }
    if not gov_cfg or not isinstance(gov_cfg, dict):
        return defaults
    cg = gov_cfg.get("cost_governance")
    if not isinstance(cg, dict):
        return defaults
    for k in defaults:
        v = cg.get(k)
        if isinstance(v, (int, float)) and v > 0:
            defaults[k] = float(v)
    return defaults
