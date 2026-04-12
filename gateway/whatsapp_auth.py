"""
WhatsApp identifier normalization and phone↔LID alias resolution.

Used by gateway allowlists, pairing approval, and run.py authorization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from hermes_constants import get_hermes_home


def normalize_whatsapp_identifier(value: str) -> str:
    """Strip WhatsApp JID/LID syntax down to its stable numeric identifier."""
    return (
        str(value or "")
        .strip()
        .replace("+", "", 1)
        .split(":", 1)[0]
        .split("@", 1)[0]
    )


def whatsapp_bridge_session_dirs(hermes_home: Optional[Path] = None) -> list[Path]:
    """Directories where Baileys may write lid-mapping-*.json (profile layout vs legacy)."""
    home = hermes_home or get_hermes_home()
    out: list[Path] = []
    for p in (
        home / "platforms" / "whatsapp" / "session",
        home / "whatsapp" / "session",
    ):
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def expand_whatsapp_auth_aliases(
    identifier: str,
    hermes_home: Optional[Path] = None,
) -> set[str]:
    """Resolve WhatsApp phone/LID aliases using bridge session mapping files."""
    normalized = normalize_whatsapp_identifier(identifier)
    if not normalized:
        return set()

    resolved: set[str] = set()
    queue = [normalized]

    while queue:
        current = queue.pop(0)
        if not current or current in resolved:
            continue

        resolved.add(current)
        for suffix in ("", "_reverse"):
            mapped: str | None = None
            for session_dir in whatsapp_bridge_session_dirs(hermes_home):
                mapping_path = session_dir / f"lid-mapping-{current}{suffix}.json"
                if not mapping_path.exists():
                    continue
                try:
                    mapped = normalize_whatsapp_identifier(
                        json.loads(mapping_path.read_text(encoding="utf-8"))
                    )
                    break
                except Exception:
                    continue
            if mapped and mapped not in resolved:
                queue.append(mapped)

    return resolved
