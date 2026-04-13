"""Persistent calendar-day spend tracking in USD (for API estimates), display in AUD.

Driven by ``routing_canon`` ``hard_budget`` (see ``agent/dynamic_routing_canon.yaml``).
State file: ``${HERMES_HOME}/workspace/memory/runtime/operations/daily_budget_state.json``.

Daily rollover and the TUI “reset in …” countdown use ``hard_budget.reset_timezone``
(IANA name, default ``Australia/Sydney``) so VPS UTC clocks still match operator locale.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STATE_NAME = "daily_budget_state.json"


class HardBudgetBlockedError(RuntimeError):
    """Raised when the daily hard budget blocks an LLM call (denied or no approval)."""


# Clarify choice labels (operator picks one substring match).
HARD_BUDGET_APPROVE_CHOICE = "approve"
HARD_BUDGET_DENY_CHOICE = "deny"


def hours_until_local_midnight() -> float:
    """Hours from now until next midnight in the process local timezone (0–24)."""
    now = datetime.now().astimezone()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(0.0, (nxt - now).total_seconds() / 3600.0)


def hours_until_timezone_midnight(zone_name: str) -> float:
    """Hours until next midnight in *zone_name* (IANA). Falls back to local on bad tz."""
    zn = (zone_name or "").strip()
    if not zn:
        return hours_until_local_midnight()
    try:
        from zoneinfo import ZoneInfo

        z = ZoneInfo(zn)
        now = datetime.now(z)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(0.0, (nxt - now).total_seconds() / 3600.0)
    except Exception:
        logger.debug("hours_until_timezone_midnight: bad zone %r", zn, exc_info=True)
        return hours_until_local_midnight()


def calendar_date_in_timezone(zone_name: Optional[str]) -> str:
    """``YYYY-MM-DD`` for “today” in *zone_name*, or host local date if unset/invalid."""
    zn = (zone_name or "").strip()
    if not zn:
        return date.today().isoformat()
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(zn)).date().isoformat()
    except Exception:
        return date.today().isoformat()


def _state_path() -> Path:
    from hermes_constants import get_hermes_home

    from hermes_constants import get_workspace_operations_dir

    d = get_workspace_operations_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / STATE_NAME


@dataclass
class BudgetSnapshot:
    daily_budget_aud: float
    spent_usd_today: float
    spent_aud_today: float
    daily_cap_usd: float
    hours_to_reset: float
    turn_cost_usd: float
    enabled: bool


class BudgetLedger:
    """Tracks cumulative USD spend for the configured calendar day (timezone-aware)."""

    def __init__(
        self,
        *,
        daily_budget_aud: float,
        aud_to_usd: float,
        path: Optional[Path] = None,
        budget_timezone: Optional[str] = None,
    ):
        self.daily_budget_aud = max(0.01, float(daily_budget_aud))
        self.aud_to_usd = max(1e-9, float(aud_to_usd))
        self.daily_cap_usd = self.daily_budget_aud * self.aud_to_usd
        self._path = path or _state_path()
        self._budget_tz = (budget_timezone or "").strip() or None
        self._spent_today = 0.0
        self._loaded_date = ""
        self._load_or_roll()

    def _today_key(self) -> str:
        return calendar_date_in_timezone(self._budget_tz)

    def _load_or_roll(self) -> None:
        today = self._today_key()
        if not self._path.is_file():
            self._spent_today = 0.0
            self._loaded_date = today
            self._persist_unlocked()
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("budget_ledger: read failed %s: %s", self._path, e)
            self._spent_today = 0.0
            self._loaded_date = today
            self._persist_unlocked()
            return
        if not isinstance(data, dict):
            data = {}
        file_date = str(data.get("date") or "")
        if file_date != today:
            self._spent_today = 0.0
            self._loaded_date = today
            self._persist_unlocked()
            return
        try:
            self._spent_today = max(0.0, float(data.get("spent_usd") or 0.0))
        except (TypeError, ValueError):
            self._spent_today = 0.0
        self._loaded_date = today

    def _persist_unlocked(self) -> None:
        payload = {
            "date": self._loaded_date or self._today_key(),
            "spent_usd": round(self._spent_today, 6),
            "daily_budget_aud": self.daily_budget_aud,
            "aud_to_usd": self.aud_to_usd,
        }
        if self._budget_tz:
            payload["budget_timezone"] = self._budget_tz
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".daily_budget_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=0)
                    f.write("\n")
                Path(tmp).replace(self._path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.debug("budget_ledger: persist failed: %s", e)

    def refresh_if_new_day(self) -> None:
        if self._today_key() != self._loaded_date:
            self._load_or_roll()

    def add_spend_usd(self, delta_usd: float) -> None:
        if delta_usd <= 0:
            return
        today = self._today_key()
        try:
            import fcntl  # type: ignore
        except ImportError:
            fcntl = None  # type: ignore
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch(exist_ok=True)
            with open(self._path, "r+", encoding="utf-8") as f:
                if fcntl is not None:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    except OSError:
                        pass
                try:
                    raw = (f.read() or "").strip()
                    data: Dict[str, Any] = {}
                    if raw:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            data = {}
                    file_date = str(data.get("date") or "")
                    spent = 0.0
                    if file_date == today:
                        try:
                            spent = max(0.0, float(data.get("spent_usd") or 0.0))
                        except (TypeError, ValueError):
                            spent = 0.0
                    spent += float(delta_usd)
                    self._spent_today = spent
                    self._loaded_date = today
                    payload = {
                        "date": today,
                        "spent_usd": round(spent, 6),
                        "daily_budget_aud": self.daily_budget_aud,
                        "aud_to_usd": self.aud_to_usd,
                    }
                    if self._budget_tz:
                        payload["budget_timezone"] = self._budget_tz
                    f.seek(0)
                    f.truncate()
                    json.dump(payload, f, indent=0)
                    f.write("\n")
                    f.flush()
                finally:
                    if fcntl is not None:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        except OSError:
                            pass
        except Exception as e:
            logger.debug("budget_ledger: add_spend failed: %s", e)
            self.refresh_if_new_day()
            self._spent_today += float(delta_usd)
            self._persist_unlocked()

    @property
    def spent_usd_today(self) -> float:
        self.refresh_if_new_day()
        return self._spent_today

    def spent_aud_today(self) -> float:
        return self.spent_usd_today / self.aud_to_usd

    def is_daily_exhausted(self) -> bool:
        return self.spent_usd_today >= self.daily_cap_usd

    def snapshot(
        self,
        *,
        turn_cost_usd: float = 0.0,
        enabled: bool = True,
    ) -> BudgetSnapshot:
        self.refresh_if_new_day()
        su = self.spent_usd_today
        if self._budget_tz:
            h_reset = hours_until_timezone_midnight(self._budget_tz)
        else:
            h_reset = hours_until_local_midnight()
        return BudgetSnapshot(
            daily_budget_aud=self.daily_budget_aud,
            spent_usd_today=su,
            spent_aud_today=su / self.aud_to_usd,
            daily_cap_usd=self.daily_cap_usd,
            hours_to_reset=h_reset,
            turn_cost_usd=max(0.0, float(turn_cost_usd)),
            enabled=enabled,
        )


def format_budget_bar_text(snap: BudgetSnapshot, *, max_width: int = 120) -> str:
    if not snap.enabled:
        return ""
    h = snap.hours_to_reset
    h_int = int(h)
    m_int = int((h - h_int) * 60)
    line = (
        f"💳 turn ~${snap.turn_cost_usd:.3f} │ "
        f"daily {snap.spent_aud_today:.2f}/{snap.daily_budget_aud:.2f} AUD "
        f"(${snap.spent_usd_today:.2f}/${snap.daily_cap_usd:.2f}) │ "
        f"reset in {h_int}h{m_int:02d}m"
    )
    if len(line) > max_width:
        line = line[: max(0, max_width - 1)] + "…"
    return line
