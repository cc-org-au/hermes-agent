#!/usr/bin/env python3
"""Strip **secrets** from social/chat lines in Hermes ``.env`` files (keep allowlist / ID lines).

Scans ``HERMES_HOME`` (default: ``~/.hermes``) recursively for files named ``.env``.
Removes variables that are messaging **tokens/secrets** (``password: true`` in
``OPTIONAL_ENV_VARS`` for category ``messaging``), plus a small set of secrets that
only appear in ``_EXTRA_ENV_KEYS`` (Feishu, Matrix password, Twilio auth, etc.).

**Keeps** allowlists and identifiers: ``TELEGRAM_ALLOWED_*``, ``SLACK_ALLOWED_*``,
``DISCORD_ALLOWED_*``, ``*_HOME_CHANNEL*``, ``MATRIX_USER_ID``, ``MATTERMOST_URL``,
``GATEWAY_ALLOW_ALL_USERS``, boolean/UX flags like ``SLACK_NOTIFY_*``, and the
API server / webhook entries listed in ``_KEEP_MESSAGING_KEYS``.

Also keeps ``TELEGRAM_WEBHOOK_URL`` / ``TELEGRAM_WEBHOOK_PORT``; removes
``TELEGRAM_WEBHOOK_SECRET`` only.

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

# Not removed: local API server, inbound webhook adapter, per-host gateway lock id.
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

# Messaging-related secrets listed in _EXTRA_ENV_KEYS / SMS / webhook secret (not full OPTIONAL rows).
_EXTRA_MESSAGING_SECRET_KEYS = frozenset(
    {
        "MATRIX_PASSWORD",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_ACCOUNT_SID",  # paired with auth token for SMS; strip to avoid overlap
        "TELEGRAM_WEBHOOK_SECRET",
        "FEISHU_APP_SECRET",
        "FEISHU_ENCRYPT_KEY",
        "FEISHU_VERIFICATION_TOKEN",
        "DINGTALK_CLIENT_SECRET",
        "WECOM_SECRET",
    }
)


def _messaging_secret_key_names() -> frozenset[str]:
    from hermes_cli.config import OPTIONAL_ENV_VARS

    out: set[str] = set(_EXTRA_MESSAGING_SECRET_KEYS)
    for name, meta in OPTIONAL_ENV_VARS.items():
        if not isinstance(meta, dict):
            continue
        if meta.get("category") != "messaging":
            continue
        if name in _KEEP_MESSAGING_KEYS:
            continue
        if meta.get("password") is True:
            out.add(name)
    return frozenset(out)


def _should_remove_secret_line(key: str, secret_keys: frozenset[str]) -> bool:
    return key in secret_keys


def _process_file(path: Path, *, secret_keys: frozenset[str], dry_run: bool) -> tuple[int, bool]:
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
        if _should_remove_secret_line(key, secret_keys):
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

    secret_keys = _messaging_secret_key_names()
    total_removed = 0
    files_changed = 0
    for env_path in sorted(root.rglob(".env")):
        if not env_path.is_file():
            continue
        try:
            n, changed = _process_file(
                env_path, secret_keys=secret_keys, dry_run=args.dry_run
            )
        except OSError as e:
            print(f"error: {env_path}: {e}", file=sys.stderr)
            return 1
        if n:
            rel = env_path.relative_to(root)
            print(
                f"{'would remove' if args.dry_run else 'removed'} {n} secret line(s): {rel}"
            )
            total_removed += n
            if changed:
                files_changed += 1

    suffix = " (dry-run)" if args.dry_run else ""
    print(
        f"Done{suffix}: {files_changed} file(s), {total_removed} messaging-secret line(s) removed "
        f"(allowlist / ID vars kept)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
