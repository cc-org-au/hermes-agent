#!/usr/bin/env python3
"""Create operations/*.md stubs if missing (does not overwrite)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _resolve_workspace_root() -> Path:
    """Resolve where memory/runtime/operations/ should be created."""
    explicit = os.environ.get("AGENT_WORKSPACE_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return REPO

STUBS = [
    "README.md",
    "ORG_REGISTRY.md",
    "ORG_CHART.md",
    "AGENT_LIFECYCLE_REGISTER.md",
    "TASK_STATE_STANDARD.md",
    "BOARD_REVIEW_REGISTER.md",
    "CHANNEL_ARCHITECTURE.md",
    "SECURITY_ALERT_REGISTER.md",
    "SECURITY_AUDIT_REPORT.md",
    "SECURITY_REMEDIATION_QUEUE.md",
    "INCIDENT_REGISTER.md",
]

HEADER = """# {title}

> Stub created by `policies/core/scripts/init_operations_stubs.py`. Replace with operational content.

"""


def main() -> int:
    workspace_root = _resolve_workspace_root()
    ops = workspace_root / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True, exist_ok=True)
    print("operations root:", ops)
    proj = workspace_root / "memory" / "knowledge" / "projects"
    proj.mkdir(parents=True, exist_ok=True)
    created = 0
    for name in STUBS:
        path = ops / name
        if path.exists():
            continue
        title = name.replace(".md", "").replace("_", " ")
        path.write_text(HEADER.format(title=title), encoding="utf-8")
        created += 1
        try:
            rel = path.relative_to(REPO)
        except ValueError:
            rel = path
        print("created", rel)
    if created == 0:
        print("init_operations_stubs: nothing to create (all present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
