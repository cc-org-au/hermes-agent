"""
Optional notification when a root agent turn completes (e.g. HTTP GET to a Mac listener).

Set on the machine that runs Hermes (e.g. droplet ``~/.hermes/.env``)::

    HERMES_TURN_DONE_NOTIFY_URL=http://100.x.y.z:8765/

where ``100.x.y.z`` is your Mac's Tailscale IP and a tiny local server plays a sound.
Outbound-only from VPS — no open ports on the server.

If ``os.environ`` has a stale empty value for the key, we re-read ``~/.hermes/.env``
(and profile ``.env`` when applicable) so the URL is still found.

**Reliability:** If the VPS cannot open a TCP connection to your Mac (sleep, firewall,
IDE-only listener, Tailscale quirks), use an **SSH reverse tunnel** instead: on the Mac,
``ssh -N -R 8765:127.0.0.1:8765 user@vps`` and set
``HERMES_TURN_DONE_NOTIFY_URL=http://127.0.0.1:8765/`` on the VPS. See ``AGENTS.md``.

Does not run for delegate/subagent ``run_conversation`` completions (``_delegate_depth`` > 0).
"""

from __future__ import annotations

import logging
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# urllib must complete; Tailscale first packet + Mac wake can exceed 2.5s
_DEFAULT_TIMEOUT_SEC = 8.0


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
    return out


def _merge_hermes_env_files() -> dict[str, str]:
    """Merge root ``~/.hermes/.env`` then profile ``.env`` (profile wins on duplicate keys)."""
    try:
        from hermes_constants import get_hermes_home
    except Exception:
        return {}

    home = get_hermes_home()
    merged: dict[str, str] = {}
    parts = home.parts
    if "profiles" in parts:
        try:
            pi = parts.index("profiles")
            root_env = Path(*parts[:pi]) / ".env"
            if root_env.is_file():
                merged.update(_parse_env_file(root_env))
        except (ValueError, OSError):
            pass
    prof_env = home / ".env"
    if prof_env.is_file():
        merged.update(_parse_env_file(prof_env))
    return merged


def _resolve_turn_done_notify_url() -> str:
    """Prefer ``os.environ``; if missing or blank, merge Hermes ``.env`` files on disk."""
    raw = os.getenv("HERMES_TURN_DONE_NOTIFY_URL")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip()
    merged = _merge_hermes_env_files()
    return (merged.get("HERMES_TURN_DONE_NOTIFY_URL") or "").strip()


def _redact_url_for_log(url: str) -> str:
    """Avoid logging full host; keep scheme + host shape for support."""
    try:
        m = re.match(r"^(https?://)([^/]+)(.*)$", url, re.I)
        if not m:
            return "(invalid)"
        host = m.group(2)
        if len(host) > 48:
            host = host[:20] + "…"
        return f"{m.group(1)}{host}{m.group(3) or '/'}"
    except Exception:
        return "(redacted)"


def maybe_notify_turn_done(
    *,
    agent: object,
    final_response: object,
    interrupted: bool,
) -> None:
    """Fire-and-forget GET to ``HERMES_TURN_DONE_NOTIFY_URL`` if configured."""
    if interrupted:
        return
    if not final_response:
        return
    if getattr(agent, "_delegate_depth", 0) != 0:
        return

    url = _resolve_turn_done_notify_url()
    if not url:
        return

    try:
        timeout = float(os.getenv("HERMES_TURN_DONE_NOTIFY_TIMEOUT", "") or _DEFAULT_TIMEOUT_SEC)
    except ValueError:
        timeout = _DEFAULT_TIMEOUT_SEC

    def _run() -> None:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()
            logger.debug("turn_done_notify ok %s", _redact_url_for_log(url))
        except urllib.error.HTTPError as e:
            logger.warning(
                "turn_done_notify HTTP %s for %s — check listener / tunnel",
                e.code,
                _redact_url_for_log(url),
            )
        except Exception as e:
            logger.warning(
                "turn_done_notify failed (%s) for %s — Mac listener running? SSH -R tunnel? Tailscale?",
                e,
                _redact_url_for_log(url),
            )

    threading.Thread(target=_run, daemon=True, name="hermes-turn-done-notify").start()
