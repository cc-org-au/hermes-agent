#!/usr/bin/env python3
"""Generate ``messaging_role_routing.yaml`` and refresh ``role_assignments.yaml``.

Binds allowlisted channel/chat IDs from ``HERMES_HOME/.env`` to messaging role
slugs using ``workspace/operations/messaging_channel_role_map.yaml`` (see
template). Role slugs receive ``allowed_toolsets`` and ``policy_reads`` from
``scripts/core/org_agent_profiles_manifest.yaml`` plus the token-model and
channel-architecture standards (paths as ``POLICY_ROOT/...``).

Usage::

  ./venv/bin/python scripts/core/sync_messaging_governance.py [--dry-run]

Requires active ``HERMES_HOME`` (profile). Does not print secrets.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

STANDARD_POLICY_READS = [
    "POLICY_ROOT/core/governance/standards/token-model-tool-and-channel-governance-policy.md",
    "POLICY_ROOT/core/governance/standards/channel-architecture-policy.md",
    "POLICY_ROOT/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_allowlist(val: str) -> list[str]:
    return [p.strip() for p in (val or "").split(",") if p.strip()]


def _policy_path_from_role_prompt(rp: str) -> str:
    s = (rp or "").strip().lstrip("/")
    if s.startswith("policies/"):
        rest = s[len("policies/") :].lstrip("/")
        return f"POLICY_ROOT/{rest}"
    if s.startswith("POLICY_ROOT/"):
        return s
    return f"POLICY_ROOT/{s}" if s else ""


def _load_manifest(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def build_roles_from_manifest(manifest: dict[str, Any], chief_toolsets: list[str]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list):
        profiles = []

    reads_chief = list(STANDARD_POLICY_READS) + [
        "POLICY_ROOT/core/chief-orchestrator-directive.md",
    ]
    roles["chief_orchestrator"] = {
        "display_name": "Chief Orchestrator",
        "policy_reads": reads_chief,
        "hermes_profile_for_delegation": "chief-orchestrator",
        "allowed_toolsets": chief_toolsets,
    }

    for p in profiles:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        slug = name.strip()
        toolsets = p.get("toolsets")
        if not isinstance(toolsets, list):
            toolsets = []
        ts = [str(x).strip() for x in toolsets if str(x).strip()]
        reads = list(STANDARD_POLICY_READS)
        rp = p.get("role_prompt")
        if isinstance(rp, str) and rp.strip():
            pp = _policy_path_from_role_prompt(rp)
            if pp and pp not in reads:
                reads.append(pp)
        roles[slug] = {
            "display_name": slug.replace("-", " ").replace("_", " ").title(),
            "policy_reads": reads,
            "hermes_profile_for_delegation": slug,
            "allowed_toolsets": ts,
        }
    return roles


def merge_role_assignments(
    existing: dict[str, Any] | None,
    generated: dict[str, Any],
) -> dict[str, Any]:
    """Overwrite manifest/chief-generated roles; keep unknown user-defined roles."""
    ver = 1
    if isinstance(existing, dict) and isinstance(existing.get("version"), int):
        ver = existing["version"]
    out_roles: dict[str, Any] = {}
    if isinstance(existing, dict):
        er = existing.get("roles")
        if isinstance(er, dict):
            for k, v in er.items():
                if k not in generated and not str(k).startswith("_"):
                    out_roles[k] = v
    for k, v in generated.items():
        out_roles[k] = v
    return {"version": ver, "roles": out_roles}


def build_role_routing_from_env_and_map(
    env: dict[str, str],
    map_doc: dict[str, Any],
) -> dict[str, Any]:
    defaults = map_doc.get("defaults") if isinstance(map_doc.get("defaults"), dict) else {}
    def_slack = str(defaults.get("slack") or defaults.get("slack_role") or "chief_orchestrator").strip()
    def_telegram = str(
        defaults.get("telegram") or defaults.get("telegram_role") or "chief_orchestrator"
    ).strip()
    def_whatsapp = str(
        defaults.get("whatsapp") or defaults.get("whatsapp_role") or "chief_orchestrator"
    ).strip()
    def_discord = str(
        defaults.get("discord") or defaults.get("discord_role") or "chief_orchestrator"
    ).strip()

    slack_map = map_doc.get("slack_channels") or map_doc.get("slack")
    if not isinstance(slack_map, dict):
        slack_map = {}
    tg_map = map_doc.get("telegram_chats") or map_doc.get("telegram")
    if not isinstance(tg_map, dict):
        tg_map = {}
    wa_map = map_doc.get("whatsapp_chats") or map_doc.get("whatsapp")
    if not isinstance(wa_map, dict):
        wa_map = {}
    dc_map = map_doc.get("discord_channels") or map_doc.get("discord")
    if not isinstance(dc_map, dict):
        dc_map = {}

    def map_id(cid: str, table: dict[str, Any], default_slug: str) -> str:
        mapped = table.get(cid)
        if mapped is None:
            mapped = table.get(str(cid).strip())
        if mapped is None:
            return default_slug
        return str(mapped).strip()

    slack_channels: dict[str, str] = {}
    for cid in _parse_allowlist(env.get("SLACK_ALLOWED_CHANNELS", "")):
        slack_channels[cid] = map_id(cid, slack_map, def_slack)

    telegram_chats: dict[str, str] = {}
    for cid in _parse_allowlist(env.get("TELEGRAM_ALLOWED_CHATS", "")):
        telegram_chats[cid] = map_id(cid, tg_map, def_telegram)

    whatsapp_chats: dict[str, str] = {}
    for cid in _parse_allowlist(env.get("WHATSAPP_ALLOWED_CHATS", "")):
        whatsapp_chats[cid] = map_id(cid, wa_map, def_whatsapp)

    discord_chats: dict[str, str] = {}
    for cid in _parse_allowlist(env.get("DISCORD_ALLOWED_CHANNELS", "")):
        discord_chats[cid] = map_id(cid, dc_map, def_discord)

    threads = map_doc.get("slack_threads") or map_doc.get("threads")
    if not isinstance(threads, dict):
        threads = {}
    slack_threads: dict[str, str] = {}
    for tid, slug in threads.items():
        if isinstance(slug, str) and slug.strip():
            slack_threads[str(tid).strip()] = slug.strip()

    default_role = map_doc.get("default_role")
    if not isinstance(default_role, str) or not default_role.strip():
        default_role = def_slack

    rr: dict[str, Any] = {
        "enabled": True,
        "default_role": str(default_role).strip(),
    }
    if slack_channels or slack_threads:
        rr["slack"] = {}
        if slack_channels:
            rr["slack"]["channels"] = slack_channels
        if slack_threads:
            rr["slack"]["threads"] = slack_threads
    if telegram_chats:
        rr["telegram"] = {"chats": telegram_chats}
    if whatsapp_chats:
        rr["whatsapp"] = {"chats": whatsapp_chats}
    if discord_chats:
        rr["discord"] = {"channels": discord_chats}
    return rr


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    rs = str(root)
    if rs not in sys.path:
        sys.path.insert(0, rs)

    parser = argparse.ArgumentParser(description="Sync messaging routing from .env + channel map.")
    parser.add_argument("--dry-run", action="store_true", help="Print YAML only; do not write files")
    args = parser.parse_args(argv)

    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    ops = home / "workspace" / "operations"
    env_path = home / ".env"
    map_path = ops / "messaging_channel_role_map.yaml"
    manifest_path = _repo_root() / "scripts" / "core" / "org_agent_profiles_manifest.yaml"

    if not manifest_path.is_file():
        print(f"Missing manifest: {manifest_path}", file=sys.stderr)
        return 1

    env = _parse_dotenv(env_path)
    if map_path.is_file():
        map_doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    else:
        map_doc = {}
        print(
            f"Warning: {map_path} missing — using defaults only (chief_orchestrator).",
            file=sys.stderr,
        )
    if not isinstance(map_doc, dict):
        map_doc = {}

    try:
        from hermes_cli.config import load_config
        from hermes_cli.tools_config import _get_platform_tools

        full_cfg = load_config()
        chief_ts = sorted(_get_platform_tools(full_cfg, "slack"))
    except Exception as exc:
        print(f"Could not resolve chief toolsets from config: {exc}", file=sys.stderr)
        chief_ts = []

    manifest = _load_manifest(manifest_path)
    generated_roles = build_roles_from_manifest(manifest, chief_ts)

    assign_path = ops / "role_assignments.yaml"
    existing_doc: dict[str, Any] = {}
    if assign_path.is_file():
        try:
            existing_doc = yaml.safe_load(assign_path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing_doc = {}
    merged_assign = merge_role_assignments(
        existing_doc if isinstance(existing_doc, dict) else {},
        generated_roles,
    )

    rr = build_role_routing_from_env_and_map(env, map_doc)
    overlay_doc = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role_routing": rr,
    }

    if args.dry_run:
        print(yaml.safe_dump(merged_assign, default_flow_style=False, allow_unicode=True, sort_keys=False))
        print("---")
        print(yaml.safe_dump(overlay_doc, default_flow_style=False, allow_unicode=True, sort_keys=False))
        return 0

    ops.mkdir(parents=True, exist_ok=True)
    assign_path.write_text(
        yaml.safe_dump(merged_assign, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (ops / "messaging_role_routing.yaml").write_text(
        yaml.safe_dump(overlay_doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {assign_path}")
    print(f"Wrote {ops / 'messaging_role_routing.yaml'}")
    print("Restart gateway to pick up routing / role_assignments changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
