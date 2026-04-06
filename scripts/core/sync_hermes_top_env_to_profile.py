#!/usr/bin/env python3
"""Merge ~/.hermes/.env into a profile's ``HERMES_HOME/.env``.

Keys from the **top-level** ``~/.hermes/.env`` overwrite the same key in the
profile file. Keys that exist **only** in the profile file are kept.

This matches the usual VPS pattern: edit shared secrets under ``~/.hermes/.env``,
then sync into ``profiles/chief-orchestrator/.env`` so the gateway / ``-p chief``
runtime sees them.

Usage::

    ./venv/bin/python scripts/core/sync_hermes_top_env_to_profile.py
    ./venv/bin/python scripts/core/sync_hermes_top_env_to_profile.py --profile chief-orchestrator

    # Explicit paths
    ./venv/bin/python scripts/core/sync_hermes_top_env_to_profile.py \\
        --top /home/hermesuser/.hermes/.env \\
        --profile-env /home/hermesuser/.hermes/profiles/chief-orchestrator/.env
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

_LINE_RE = re.compile(
    r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$"
)


def _parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return (key->value, key order as first seen)."""
    if not path.exists():
        return {}, []
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    order: list[str] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        # Strip matching quotes from value
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k not in out:
            order.append(k)
        out[k] = v
    return out, order


def _format_line(key: str, value: str) -> str:
    if not value:
        return f'{key}=""'
    if re.search(r'[\s#"\'\\$`]', value) or value.startswith("#"):
        esc = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{esc}"'
    return f"{key}={value}"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if content.endswith("\n") else content + "\n"
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge top-level ~/.hermes/.env into a profile .env (top wins on duplicate keys)."
    )
    ap.add_argument(
        "--profile",
        default="chief-orchestrator",
        help="Profile name under ~/.hermes/profiles/ (default: chief-orchestrator)",
    )
    ap.add_argument("--top", type=Path, help="Top-level .env (default: ~/.hermes/.env)")
    ap.add_argument("--profile-env", type=Path, help="Profile .env path (default: profiles/<profile>/.env)")
    args = ap.parse_args()

    home = Path.home()
    top_path = args.top or (home / ".hermes" / ".env")
    if args.profile_env:
        prof_path = args.profile_env.expanduser()
    else:
        prof_path = home / ".hermes" / "profiles" / args.profile / ".env"

    top, top_order = _parse_env(top_path.expanduser())
    prof, prof_order = _parse_env(prof_path)

    if not top and not prof:
        print(f"Nothing to sync: missing or empty {top_path} and {prof_path}", flush=True)
        return 1

    # Top keys overwrite; keep profile-only keys
    merged: dict[str, str] = dict(prof)
    merged.update(top)

    # Order: top keys in top file order, then profile-only keys in profile order
    top_set = set(top.keys())
    prof_only = [k for k in prof_order if k not in top_set]
    key_order = [k for k in top_order if k in merged] + [k for k in prof_only if k in merged]

    lines = [
        "# Synced by sync_hermes_top_env_to_profile.py — top-level ~/.hermes/.env merged into this profile.",
        "# Top-level keys overwrite; profile-only keys are preserved.",
        "",
    ]
    for k in key_order:
        lines.append(_format_line(k, merged[k]))
    body = "\n".join(lines) + "\n"

    _atomic_write(prof_path.expanduser(), body)
    print(
        f"Updated {prof_path} ({len(merged)} key(s); top file {top_path}).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
