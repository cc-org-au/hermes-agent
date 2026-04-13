"""Load concise runtime governance directives from workspace memory runtime operations.

Chief / HR (or automation) edit ``runtime_governance.runtime.yaml`` under the
active ``HERMES_HOME``. The block is injected into project context on every
**new** agent construction (CLI + gateway) so phased activation and policy
read-order need not be pasted manually.

File (optional): ``HERMES_HOME/workspace/memory/runtime/operations/runtime_governance.runtime.yaml``
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_workspace_operations_dir

logger = logging.getLogger(__name__)


def runtime_governance_path() -> Path:
    return get_workspace_operations_dir() / "runtime_governance.runtime.yaml"


def load_runtime_governance_prompt(*, max_chars: int = 6000) -> str:
    """Return markdown to append to project context, or "" if missing/disabled."""
    path = runtime_governance_path()
    if not path.is_file():
        return ""
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("runtime governance: could not load %s: %s", path, exc)
        return ""

    if not isinstance(raw, dict):
        return ""

    if not _truthy(raw.get("enabled", True)):
        return ""

    lines: List[str] = [
        "## Runtime governance (memory runtime operations)",
        "",
        "The operator or org controller maintains this block on disk — follow it "
        "without asking for large policy pastes. Use file tools to read the paths below.",
        "",
    ]

    ver = raw.get("version")
    if ver is not None:
        lines.append(f"- **Config version:** {ver}")
    sess = raw.get("activation_session")
    if sess is not None:
        lines.append(f"- **Activation session (phased runbook):** {sess}")
    role = raw.get("active_role_slug") or raw.get("assigned_role")
    if role:
        lines.append(f"- **Assigned role slug:** `{role}`")
    by = raw.get("assigned_by")
    if by:
        lines.append(f"- **Assigned by:** {by}")

    summary = (raw.get("summary") or "").strip()
    if summary:
        lines.extend(["", "### Summary", "", summary, ""])

    directives = raw.get("directives") or raw.get("concise_directives")
    if isinstance(directives, list) and directives:
        lines.append("### Binding directives")
        lines.append("")
        for item in directives:
            if isinstance(item, str) and item.strip():
                lines.append(f"- {item.strip()}")
        lines.append("")

    reads = raw.get("read_order_paths") or raw.get("policy_reads")
    if isinstance(reads, list) and reads:
        lines.append("### Read with tools (do not paste full files into chat)")
        lines.append("")
        for item in reads:
            if isinstance(item, str) and item.strip():
                lines.append(f"- `{item.strip()}`")
        lines.append("")

    notes = (raw.get("notes") or "").strip()
    if notes:
        lines.extend(["### Notes", "", notes, ""])

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… (truncated)"
    return text + "\n\n"


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
