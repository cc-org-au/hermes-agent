#!/usr/bin/env python3
"""Remove social/chat messaging credentials from Hermes ``.env`` files.

Scans ``HERMES_HOME`` (default: ``~/.hermes``) recursively for files named ``.env``.
Drops variables that belong to chat/messaging platforms (Telegram, Slack, Discord,
WhatsApp, Signal, Matrix, Mattermost, Feishu, WeCom, DingTalk, SMS/Twilio, etc.)
based on ``hermes_cli.config.OPTIONAL_ENV_VARS`` (category ``messaging``), while
**keeping** API server, webhook adapter, and ``HERMES_GATEWAY_LOCK_INSTANCE`` entries.

Also removes lines whose keys start with ``TELEGRAM_WEBHOOK_`` (webhook mode) and
``GATEWAY_ALLOWED_USERS`` / ``GATEWAY_ALLOW_ALL_USERS`` if still present under other names.

Usage (from repo root, venv active)::

    ./venv/bin/python scripts/core/strip_messaging_env_from_hermes_home.py
    ./venv/bin/python scripts/core/strip_messaging_env_from_hermes_home.py /path/to/hermes/home

Dry-run::

    ./venv/bin/python scripts/core/strip_messaging_env_from_hermes_home.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

_ENV_LINE_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")

# Not removed: local API server, inbound webhook adapter config, per-host lock id.
_KEEP_MESSAGING_KEYS = frozenset(
    {
        "HERMES_GATEWAY_LOCK_INSTANCE",
        "API_SERVER_ENABLED",
        "API_SERVER_KEY",
        "API_SERVER_PORT",
        "API_SERVER_HOST",
        "API_SERVER_CORS_ORIGINS",
        "WEBHOOK_ENABLED",
        "WEBHOOK_PORT",
        "WEBHOOK_SECRET",
    }
)

_EXTRA_STRIP_PREFIXES = (
    "TELEGRAM_WEBHOOK_",
)


def _strip_key_names() -> frozenset[str]:
    from hermes_cli.config import OPTIONAL_ENV_VARS

    out: set[str] = set()
    for name, meta in OPTIONAL_ENV_VARS.items():
        if not isinstance(meta, dict):
            continue
        if meta.get("category") != "messaging":
            continue
        if name in _KEEP_MESSAGING_KEYS:
            continue
        out.add(name)
    return frozenset(out)


def _should_remove_line(key: str, strip_names: frozenset[str]) -> bool:
    if key in strip_names:
        return True
    for prefix in _EXTRA_STRIP_PREFIXES:
        if key.startswith(prefix):
            return True
    return False


def _process_file(path: Path, *, strip_names: frozenset[str], dry_run: bool) -> tuple[int, bool]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return 0, False
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1", errors="replace")

    removed = 0
    kept: list[str] = []
    for line in raw.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        m = _ENV_LINE_KEY_RE.match(line)
        if not m:
            kept.append(line)
            continue
        key = m.group(1)
        if _should_remove_line(key, strip_names):
            removed += 1
            continue
        kept.append(line)

    if removed == 0:
        return 0, False

    new_body = "".join(kept)
    if dry_run:
        return removed, True

    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=".env.strip.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_body)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return removed, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "hermes_home",
        nargs="?",
        default=str(Path.home() / ".hermes"),
        help="HERMES_HOME root to scan (default: ~/.hermes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing files",
    )
    args = parser.parse_args()
    root = Path(args.hermes_home).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    strip_names = _strip_key_names()
    total_removed = 0
    files_changed = 0
    for env_path in sorted(root.rglob(".env")):
        if not env_path.is_file():
            continue
        # Skip accidental hits under unusual trees
        try:
            n, changed = _process_file(
                env_path, strip_names=strip_names, dry_run=args.dry_run
            )
        except OSError as e:
            print(f"error: {env_path}: {e}", file=sys.stderr)
            return 1
        if n:
            rel = env_path.relative_to(root)
            print(f"{'would strip' if args.dry_run else 'stripped'} {n} line(s): {rel}")
            total_removed += n
            if changed:
                files_changed += 1

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"Done{suffix}: {files_changed} file(s), {total_removed} line(s) removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
