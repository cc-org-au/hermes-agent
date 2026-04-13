"""Resolve per-surface messaging role slugs for ephemeral system prompt injection.

One Slack / Telegram / WhatsApp bot can serve multiple *organizational personas* by
routing channel/thread/chat identifiers to a **role slug**. Bindings and required
policy reads live in ``workspace/memory/runtime/operations/role_assignments.yaml``.

Hermes still uses a single gateway ``HERMES_HOME`` (one token set). Personas are
enforced via prompt + disk reads, not separate bot installs. For hard isolation
(separate memories, credentials), run additional profiles with their own gateway
units instead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from gateway.config import Platform
from gateway.session import SessionSource
from hermes_constants import resolve_workspace_operations_dir

logger = logging.getLogger(__name__)


def _role_assignments_path(hermes_home: Path) -> Path:
    return resolve_workspace_operations_dir(hermes_home) / "role_assignments.yaml"

# Surfaces where token-model §14 disclosure applies (human-visible messaging).
_DISCLOSURE_SKIP_PLATFORMS = frozenset(
    {
        Platform.LOCAL,
        Platform.API_SERVER,
        Platform.WEBHOOK,
    }
)


def messaging_disclosure_applies(platform: Optional[Platform]) -> bool:
    """True when outbound assistant text should carry the §14 disclosure line."""
    if platform is None:
        return False
    return platform not in _DISCLOSURE_SKIP_PLATFORMS


def append_token_model_disclosure_line(content: str, exact_role_name: str) -> str:
    """Append ``\\n\\n--<Exact Role Name>`` when missing (token-model §14).

    ``exact_role_name`` is the human role label (typically **Display name** from
    ``role_assignments.yaml``), without leading dashes.
    """
    if not content or not isinstance(content, str):
        return content
    name = (exact_role_name or "").strip()
    if not name:
        return content
    suffix = f"--{name}"
    stripped = content.rstrip()
    if not stripped:
        return f"{suffix}\n"
    last_line = stripped.splitlines()[-1].strip()
    if last_line == suffix or last_line.endswith(suffix):
        return content
    return f"{stripped}\n\n{suffix}"


def _get_role_entry(slug: str, hermes_home: Path) -> Optional[Dict[str, Any]]:
    path = _role_assignments_path(hermes_home)
    if not path.is_file():
        return None
    try:
        import yaml

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("role_assignments: load failed %s: %s", path, exc)
        return None
    if not isinstance(doc, dict):
        return None
    roles = doc.get("roles")
    if not isinstance(roles, dict):
        return None
    entry = roles.get(slug) or roles.get(str(slug).replace("-", "_"))
    if not isinstance(entry, dict):
        return None
    return entry


def load_role_display_name(slug: str, *, hermes_home: Path) -> Optional[str]:
    """Return ``display_name`` for a role slug, if defined in role_assignments."""
    if not slug or not str(slug).strip():
        return None
    entry = _get_role_entry(str(slug).strip(), hermes_home)
    if not entry:
        return None
    dn = entry.get("display_name")
    if isinstance(dn, str) and dn.strip():
        return dn.strip()
    return None


def resolve_messaging_disclosure_label(
    source: SessionSource,
    messaging_cfg: Dict[str, Any],
    *,
    hermes_home: Path,
) -> Optional[str]:
    """Resolve the exact role name for §14 disclosure for this message source."""
    if not isinstance(messaging_cfg, dict):
        return None
    rr = messaging_cfg.get("role_routing")
    if isinstance(rr, dict) and rr.get("enabled", True):
        slug = resolve_messaging_role_slug(source, rr, hermes_home=hermes_home)
        if not slug:
            dr = rr.get("default_role") or rr.get("default_slug")
            if isinstance(dr, str) and dr.strip():
                slug = dr.strip()
        if slug:
            label = load_role_display_name(slug, hermes_home=hermes_home)
            if label:
                return label
    fb = messaging_cfg.get("disclosure_fallback_display_name")
    if isinstance(fb, str) and fb.strip():
        return fb.strip()
    return None


def intersect_toolsets_with_messaging_role(
    enabled_toolsets: List[str],
    source: SessionSource,
    user_config: Dict[str, Any],
    *,
    hermes_home: Path,
) -> List[str]:
    """Intersect platform toolsets with ``role_assignments.yaml`` caps for routed slug."""
    base = list(enabled_toolsets)
    try:
        _msg_cfg = user_config.get("messaging") or {}
        _rr = _msg_cfg.get("role_routing") if isinstance(_msg_cfg, dict) else None
        _slug_cap = None
        if isinstance(_rr, dict):
            _slug_cap = resolve_messaging_role_slug(source, _rr, hermes_home=hermes_home)
        _allowed_ts = (
            load_role_allowed_toolsets(_slug_cap, hermes_home=hermes_home)
            if _slug_cap
            else None
        )
        if _allowed_ts:
            _allow_set = set(_allowed_ts)
            _inter_ts = [t for t in base if t in _allow_set]
            if _inter_ts:
                return sorted(_inter_ts)
            logger.warning(
                "Messaging role %r: allowed_toolsets ∩ platform toolsets is empty; "
                "keeping platform toolsets",
                _slug_cap,
            )
    except Exception as exc:
        logger.debug("Messaging role toolset cap skipped: %s", exc)
    return base


def load_role_allowed_toolsets(
    slug: Optional[str],
    *,
    hermes_home: Path,
) -> Optional[List[str]]:
    """Return allowed toolset names for this messaging role slug, or None for no cap.

    When ``role_assignments.yaml`` defines ``allowed_toolsets`` for the slug, the
    gateway intersects that list with the platform's configured toolsets so each
    routed persona matches org manifest / policy tool authority.
    """
    if not slug or not str(slug).strip():
        return None
    entry = _get_role_entry(str(slug).strip(), hermes_home)
    if not entry:
        return None
    raw = entry.get("allowed_toolsets")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    out: List[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out or None


def resolve_messaging_role_slug(
    source: SessionSource,
    role_routing_cfg: Dict[str, Any],
    *,
    hermes_home: Path,
) -> Optional[str]:
    """Return role slug for this message source, or None to skip extra block."""
    if not isinstance(role_routing_cfg, dict) or not role_routing_cfg.get("enabled"):
        return None

    plat = source.platform
    if plat in (Platform.LOCAL, Platform.API_SERVER, Platform.WEBHOOK):
        return None

    default = role_routing_cfg.get("default_role") or role_routing_cfg.get("default_slug")
    plat_cfg = role_routing_cfg.get(plat.value)
    if not isinstance(plat_cfg, dict):
        return str(default).strip() if default else None

    # Thread wins over channel (Slack / Discord threads)
    thread_id = (source.thread_id or "").strip()
    if thread_id:
        threads = plat_cfg.get("threads")
        if isinstance(threads, dict) and thread_id in threads:
            slug = threads.get(thread_id)
            if isinstance(slug, str) and slug.strip():
                return slug.strip()

    chat_id = str(source.chat_id or "").strip()
    if chat_id:
        chats = plat_cfg.get("chats") or plat_cfg.get("channels")
        if isinstance(chats, dict) and chat_id in chats:
            slug = chats.get(chat_id)
            if isinstance(slug, str) and slug.strip():
                return slug.strip()

    if default:
        return str(default).strip()
    return None


def load_role_assignment_block(
    slug: str,
    *,
    hermes_home: Path,
    max_chars: int = 4000,
) -> str:
    """Load role entry from role_assignments.yaml and format a short markdown block."""
    path = _role_assignments_path(hermes_home)
    if not path.is_file():
        return ""

    try:
        import yaml

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("role_assignments: load failed %s: %s", path, exc)
        return ""

    if not isinstance(doc, dict):
        return ""

    roles = doc.get("roles")
    if not isinstance(roles, dict):
        return ""

    entry = roles.get(slug) or roles.get(str(slug).replace("-", "_"))
    if not isinstance(entry, dict):
        return ""

    lines: List[str] = [
        f"## Messaging role: `{slug}`",
        "",
        "You are answering **as this org role** for this surface. "
        "Stay inside published policies; use tools to read paths — do not ask the operator to paste policy packs.",
        "",
    ]

    dn = entry.get("display_name")
    if isinstance(dn, str) and dn.strip():
        lines.append(f"- **Display name:** {dn.strip()}")

    # Token-model §14 — disclosure line (exact role name = Display name when set).
    role_label = (dn.strip() if isinstance(dn, str) and dn.strip() else slug.replace("_", " ").title())
    lines.extend(
        [
            "",
            "### Human-visible disclosure (token-model §14)",
            "",
            f"End every reply the operator can see with a final line exactly: `--{role_label}` "
            f"(use the **Display name** above verbatim when it is set).",
            "",
        ]
    )

    scope = entry.get("scope") or entry.get("mission")
    if isinstance(scope, str) and scope.strip():
        lines.extend(["", "### Scope", "", scope.strip(), ""])

    reads = entry.get("policy_reads") or entry.get("read_order_paths")
    if isinstance(reads, list) and reads:
        lines.append("### Read with file tools (priority order)")
        lines.append("")
        for r in reads:
            if isinstance(r, str) and r.strip():
                lines.append(f"- `{r.strip()}`")
        lines.append("")

    hp = entry.get("hermes_profile_for_delegation")
    if isinstance(hp, str) and hp.strip():
        lines.append(
            f"- **Delegation:** For work that must run under another Hermes profile, "
            f"use `delegate_task` with `hermes_profile=\"{hp.strip()}\"` when appropriate."
        )
        lines.append("")

    ats = entry.get("allowed_toolsets")
    if isinstance(ats, list) and ats:
        lines.append("### Tool authority (this surface)")
        lines.append("")
        lines.append(
            "Only the following toolsets are enabled for this routed role on this gateway "
            "(intersection with platform config): "
            + ", ".join(f"`{x}`" for x in ats if isinstance(x, str) and x.strip())
        )
        lines.append("")

    forbid = entry.get("forbidden")
    if isinstance(forbid, list) and forbid:
        lines.append("### Do not")
        lines.append("")
        for f in forbid:
            if isinstance(f, str) and f.strip():
                lines.append(f"- {f.strip()}")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… (truncated)"
    return text + "\n\n"


def build_messaging_role_ephemeral(
    source: SessionSource,
    role_routing_cfg: Dict[str, Any],
    *,
    hermes_home: Path,
) -> str:
    slug = resolve_messaging_role_slug(source, role_routing_cfg, hermes_home=hermes_home)
    if not slug:
        return ""
    block = load_role_assignment_block(slug, hermes_home=hermes_home)
    if not block:
        return (
            f"## Messaging role: `{slug}`\n\n"
            f"Bindings file missing or role undefined: `workspace/memory/runtime/operations/role_assignments.yaml` — "
            f"create it (`hermes workspace governance init`) and define `roles.{slug}`.\n\n"
        )
    return block
