#!/usr/bin/env python3
"""Interactively append secrets to a Hermes ``.env`` file without echoing values.

Designed for operator use on a VPS (e.g. droplet): secrets are read with
``getpass`` (no terminal echo). Nothing is written to stdout except prompts
and status lines — **never** the secret values.

Usage::

    # Default: ``$HERMES_HOME/.env`` (usually ~/.hermes/.env)
    ./venv/bin/python scripts/core/secure_hermes_env_append.py

    # Explicit file (e.g. top-level workspace .env on the droplet)
    ./venv/bin/python scripts/core/secure_hermes_env_append.py --file /home/hermesuser/.hermes/.env

Finish entering pairs by typing a **done** keyword as the variable name
(``done``, ``submit``, ``update``, ``quit``, ``exit``) or press Enter on
an empty name.

Lines are written as ``KEY=value`` (quoted when needed for dotenv parsers).

Duplicate keys: if the key already exists in the file, you are asked whether
to **replace** that line or **skip**.

Examples::

    Variable name (or 'done' to finish): HUGGINGFACE_API_KEY
    Value for HUGGINGFACE_API_KEY: [hidden]
    Variable name (or 'done' to finish): done

    Appended 1 line(s) to /home/hermesuser/.hermes/.env
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Env var name: letter/underscore start, then A-Z0-9_
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DONE_NAMES = frozenset(
    {"done", "submit", "update", "quit", "exit", "q", "end", "finish"}
)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _format_env_line(key: str, value: str) -> str:
    """Single KEY=value line safe for typical dotenv loaders."""
    if "\n" in value or "\r" in value:
        raise ValueError("value must not contain newlines")
    if not value:
        return f'{key}=""'
    # Quote if shell-special or whitespace
    if re.search(r'[\s#"\'\\$`]', value) or value.startswith("#"):
        esc = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{esc}"'
    return f"{key}={value}"


def _parse_existing_keys_and_lines(path: Path) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    lines: list[str] = []
    if not path.exists():
        return keys, lines
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines(keepends=True):
        lines.append(line)
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        # strip optional export
        if raw.startswith("export ") and "=" in raw:
            raw = raw[7:].lstrip()
        if "=" in raw:
            k = raw.split("=", 1)[0].strip()
            if k:
                keys.add(k)
    return keys, lines


def _lines_without_key(lines: list[str], key: str) -> list[str]:
    """Drop lines that set *key* (``KEY=`` or ``export KEY=``)."""
    prefix = key + "="
    exp = "export " + key + "="
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith(exp) or s.startswith(prefix):
            continue
        out.append(line)
    return out


def _atomic_write_text(path: Path, content: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if content.endswith("\n") else content + "\n"
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Securely append KEY=value pairs to a Hermes .env file (values not echoed)."
    )
    parser.add_argument(
        "--file",
        "-f",
        metavar="PATH",
        help="Target .env file (default: HERMES_HOME/.env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without modifying the file",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Do not add a timestamp comment before appended lines",
    )
    args = parser.parse_args()

    if args.file:
        env_path = Path(args.file).expanduser()
    else:
        home = os.environ.get("HERMES_HOME", "").strip()
        if home:
            env_path = Path(home) / ".env"
        else:
            env_path = Path.home() / ".hermes" / ".env"

    _err(f"Target file: {env_path}")
    _err("Variable names are shown; values are hidden. Finish with: done / submit / update (or empty name).")
    _err("")

    pending: list[tuple[str, str]] = []

    while True:
        try:
            name = input("Variable name (or 'done' to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            _err("\nAborted.")
            return 130

        if not name:
            break
        if name.lower() in _DONE_NAMES:
            break

        if not _KEY_RE.match(name):
            _err(f"Invalid name {name!r}. Use A-Z, 0-9, underscore (e.g. HUGGINGFACE_API_KEY).")
            continue

        try:
            secret = getpass.getpass(f"Value for {name}: ")
        except (EOFError, KeyboardInterrupt):
            _err("\nAborted.")
            return 130

        pending.append((name, secret))

    if not pending:
        _err("No variables entered; nothing to do.")
        return 0

    existing_keys, existing_lines = _parse_existing_keys_and_lines(env_path)
    new_lines: list[str] = list(existing_lines)
    # Ensure file ends with newline before we append
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] = new_lines[-1] + "\n"

    to_write: list[str] = []
    for key, value in pending:
        if key in existing_keys:
            try:
                ans = input(f"Key {key!r} already exists. Replace existing line? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                _err("\nAborted.")
                return 130
            if ans in ("y", "yes"):
                new_lines = _lines_without_key(new_lines, key)
                existing_keys.discard(key)
            else:
                _err(f"Skipped {key}.")
                continue
        line = _format_env_line(key, value)
        to_write.append(line)
        existing_keys.add(key)

    if not to_write:
        _err("Nothing to append after skips.")
        return 0

    banner = ""
    if not args.no_banner:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        banner = f"\n# --- secure_hermes_env_append {ts} ---\n"

    body = "".join(new_lines)
    if body and not body.endswith("\n"):
        body += "\n"
    append_block = banner + "\n".join(to_write) + "\n"
    final = body + append_block

    if args.dry_run:
        _err("[dry-run] Would write the following new line(s) (values redacted):")
        for line in to_write:
            k = line.split("=", 1)[0] if "=" in line else "?"
            _err(f"  {k}=***")
        return 0

    _atomic_write_text(env_path, final)
    _err(f"Wrote {len(to_write)} line(s) to {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
