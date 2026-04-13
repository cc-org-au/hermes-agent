"""
Deterministic cron messaging: model ends with a JSON block; only that is delivered.

Reasoning and tool narration may appear before the markers; they are never sent to the user.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Tuple

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


def try_parse_cron_delivery_envelope(
    raw: str, max_chars: int, *, strict: bool
) -> Optional[Tuple[str, bool]]:
    """
    Parse a trailing JSON envelope. Returns (text, skip_delivery) if handled.

    Returns None when no envelope is present and strict is False (caller uses legacy sanitize).

    When strict is True and the block is missing or invalid, returns ("", True).
    """
    start = raw.rfind(MARKER_START)
    if start == -1:
        if strict:
            logger.info(
                "Cron delivery: strict_delivery_envelope enabled but response has no %s block",
                MARKER_START,
            )
            return "", True
        return None

    after = raw[start + len(MARKER_START) :]
    end_idx = after.find(MARKER_END)
    if end_idx == -1:
        logger.warning("Cron delivery: %s without matching %s", MARKER_START, MARKER_END)
        if strict:
            return "", True
        return None

    chunk = _strip_optional_code_fence(after[:end_idx])
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError as e:
        logger.warning("Cron delivery: envelope JSON invalid: %s", e)
        if strict:
            return "", True
        return None

    if not isinstance(data, dict):
        if strict:
            return "", True
        return None

    silent = data.get("silent")
    if silent is True:
        return "", True

    lines = data.get("lines", None)
    if lines is None:
        if strict:
            return "", True
        return None

    if not isinstance(lines, list):
        if strict:
            return "", True
        return None

    out_lines: list[str] = []
    for i, item in enumerate(lines):
        if i >= MAX_ENVELOPE_LINES:
            break
        if not isinstance(item, str):
            if strict:
                return "", True
            return None
        t = item.strip().replace("\r\n", "\n")
        if len(t) > MAX_ENVELOPE_LINE_CHARS:
            t = t[: MAX_ENVELOPE_LINE_CHARS - 1] + "…"
        if t:
            out_lines.append(t)

    text = "\n".join(out_lines)
    if not text.strip():
        return "", True

    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"

    return text, False


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
