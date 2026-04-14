"""
Deterministic cron messaging: model ends with a JSON block; only that is delivered.

Reasoning and tool narration may appear before the markers; they are never sent to the user.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional, Tuple

from hermes_cli.config import load_config

logger = logging.getLogger(__name__)

MARKER_START = "###HERMES_CRON_DELIVERY_JSON"
MARKER_END = "###END_HERMES_CRON_DELIVERY_JSON"

MAX_ENVELOPE_LINES = 16
MAX_ENVELOPE_LINE_CHARS = 280


def _strip_optional_code_fence(s: str) -> str:
    s = s.strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if len(lines) < 2:
        return re.sub(r"^`+|`+$", "", s).strip()
    inner = "\n".join(lines[1:])
    if inner.rstrip().endswith("```"):
        inner = inner.rstrip()[:-3].rstrip()
    return inner.strip()


def _normalize_follow_up(data: Any) -> Optional[dict[str, str]]:
    if not isinstance(data, dict):
        return None

    status = str(data.get("status") or "").strip().lower()
    if status in {"", "none", "clear", "cleared"}:
        return {"status": "none", "summary": "", "requested_action": ""}

    if status in {"resolved", "closed", "done", "fixed"}:
        return {
            "status": "resolved",
            "summary": str(data.get("summary") or data.get("resolution") or "").strip(),
            "requested_action": "",
        }

    if status != "open":
        return None

    summary = str(
        data.get("summary")
        or data.get("issue")
        or data.get("blocker")
        or ""
    ).strip()
    requested_action = str(
        data.get("requested_action")
        or data.get("next_action")
        or data.get("requested_resolution")
        or ""
    ).strip()
    if not summary and not requested_action:
        return None

    return {
        "status": "open",
        "summary": summary,
        "requested_action": requested_action,
    }


def parse_cron_delivery_envelope(
    raw: str, max_chars: int, *, strict: bool
) -> Optional[dict[str, Any]]:
    """
    Parse a trailing JSON envelope.

    Returns a dict with:
      - text: sanitized text for messaging
      - skip_delivery: bool
      - follow_up: optional normalized follow-up metadata

    Returns None when no envelope is present and strict is False.
    """
    start = raw.rfind(MARKER_START)
    if start == -1:
        if strict:
            logger.info(
                "Cron delivery: strict_delivery_envelope enabled but response has no %s block",
                MARKER_START,
            )
            return {"text": "", "skip_delivery": True, "follow_up": None}
        return None

    after = raw[start + len(MARKER_START) :]
    end_idx = after.find(MARKER_END)
    if end_idx == -1:
        logger.warning("Cron delivery: %s without matching %s", MARKER_START, MARKER_END)
        if strict:
            return {"text": "", "skip_delivery": True, "follow_up": None}
        return None

    chunk = _strip_optional_code_fence(after[:end_idx])
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError as e:
        logger.warning("Cron delivery: envelope JSON invalid: %s", e)
        if strict:
            return {"text": "", "skip_delivery": True, "follow_up": None}
        return None

    if not isinstance(data, dict):
        if strict:
            return {"text": "", "skip_delivery": True, "follow_up": None}
        return None

    follow_up = _normalize_follow_up(data.get("follow_up"))

    silent = data.get("silent")
    if silent is True:
        return {"text": "", "skip_delivery": True, "follow_up": follow_up}

    lines = data.get("lines", None)
    if lines is None:
        if strict:
            return {"text": "", "skip_delivery": True, "follow_up": follow_up}
        return None

    if not isinstance(lines, list):
        if strict:
            return {"text": "", "skip_delivery": True, "follow_up": follow_up}
        return None

    out_lines: list[str] = []
    for i, item in enumerate(lines):
        if i >= MAX_ENVELOPE_LINES:
            break
        if not isinstance(item, str):
            if strict:
                return {"text": "", "skip_delivery": True, "follow_up": follow_up}
            return None
        t = item.strip().replace("\r\n", "\n")
        if len(t) > MAX_ENVELOPE_LINE_CHARS:
            t = t[: MAX_ENVELOPE_LINE_CHARS - 1] + "…"
        if t:
            out_lines.append(t)

    text = "\n".join(out_lines)
    if not text.strip():
        return {"text": "", "skip_delivery": True, "follow_up": follow_up}

    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"

    return {"text": text, "skip_delivery": False, "follow_up": follow_up}


def try_parse_cron_delivery_envelope(
    raw: str, max_chars: int, *, strict: bool
) -> Optional[Tuple[str, bool]]:
    """
    Parse a trailing JSON envelope. Returns (text, skip_delivery) if handled.

    Returns None when no envelope is present and strict is False (caller uses legacy sanitize).

    When strict is True and the block is missing or invalid, returns ("", True).
    """
    parsed = parse_cron_delivery_envelope(raw, max_chars, strict=strict)
    if parsed is None:
        return None
    return str(parsed.get("text") or ""), bool(parsed.get("skip_delivery"))


def cron_strict_delivery_envelope() -> bool:
    """
    When true, messaging requires a valid ###HERMES_CRON_DELIVERY_JSON block.

    Set HERMES_CRON_STRICT_DELIVERY_ENVELOPE=1 in the profile .env (e.g. droplet) so only
    deterministic JSON lines are delivered, without editing config.yaml.
    """
    ev = (os.environ.get("HERMES_CRON_STRICT_DELIVERY_ENVELOPE") or "").strip().lower()
    if ev in ("1", "true", "yes", "on"):
        return True
    try:
        cfg = load_config()
        return bool(cfg.get("cron", {}).get("strict_delivery_envelope", False))
    except Exception:
        return False
