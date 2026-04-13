"""Structured routing trace emission for model-selection chokepoints."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def emit_routing_decision_trace(
    *,
    stage: str,
    chosen_model: str = "",
    chosen_provider: str = "",
    reason_code: str = "",
    opm_enabled: Optional[bool] = None,
    opm_source: str = "",
    tier_source: str = "",
    skip_flags: Optional[Dict[str, Any]] = None,
    fallback_activated: Optional[bool] = None,
    explicit_user_model: Optional[bool] = None,
    profile: str = "",
    session_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "stage": stage,
        "chosen_model": chosen_model or "",
        "chosen_provider": chosen_provider or "",
        "reason_code": reason_code or "",
        "opm_enabled": bool(opm_enabled) if opm_enabled is not None else False,
        "opm_source": opm_source or "",
        "tier_source": tier_source or "",
        "skip_flags": skip_flags or {},
        "fallback_activated": bool(fallback_activated)
        if fallback_activated is not None
        else False,
        "explicit_user_model": bool(explicit_user_model)
        if explicit_user_model is not None
        else False,
        "profile": profile or "",
        "session_id": session_id or "",
    }
    if extra:
        for k, v in extra.items():
            if k not in payload:
                payload[str(k)] = v
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    # DEBUG only — avoids noisy CLI/gateway logs unless log level is turned up.
    logger.debug("[RouteTrace] %s", line)

