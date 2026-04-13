"""Org manifest sync + profile bootstrap (gated)."""

from __future__ import annotations

import json

from tools.registry import registry
from utils import env_var_enabled


def check_org_automation_tool() -> bool:
    if env_var_enabled("ORG_AUTOMATION_ALLOW_AGENT"):
        return True
    try:
        from hermes_cli.config import load_config

        oa = (load_config().get("agent") or {}).get("org_automation") or {}
        return bool(oa.get("enabled"))
    except Exception:
        return False


def sync_org_automation(
    dry_run: bool = False,
    refresh_config: bool = True,
    skip_bootstrap: bool = False,
    manifest_path: str | None = None,
    task_id: str | None = None,
) -> str:
    del task_id
    from hermes_cli.org_automation import sync_org_automation_tool

    return sync_org_automation_tool(
        dry_run=dry_run,
        refresh_config=refresh_config,
        skip_bootstrap=skip_bootstrap,
        manifest_path=manifest_path,
    )


registry.register(
    name="sync_org_automation",
    toolset="hermes_core",
    schema={
        "name": "sync_org_automation",
        "description": (
            "Apply org_agent_profiles_manifest: refresh auto-sync blocks in "
            "HERMES_HOME/workspace/memory/runtime/operations/ORG_REGISTRY.md and ORG_CHART.md, "
            "then run scripts/core/bootstrap_org_agent_profiles.py (creates/updates role profiles). "
            "Requires agent.org_automation.enabled: true in config (or ORG_AUTOMATION_ALLOW_AGENT=1). "
            "Prefer hermes workspace org-automation apply for cron/operator runs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, print planned actions only (bootstrap respects --dry-run).",
                },
                "refresh_config": {
                    "type": "boolean",
                    "description": "Pass --refresh-config to bootstrap (re-merge manifest into existing profiles).",
                },
                "skip_bootstrap": {
                    "type": "boolean",
                    "description": "Only update ORG_* markdown; do not run profile bootstrap.",
                },
                "manifest_path": {
                    "type": "string",
                    "description": "Optional path to org_agent_profiles_manifest.yaml (default: repo scripts/core/…).",
                },
            },
        },
    },
    handler=lambda args, **kw: sync_org_automation(
        dry_run=bool(args.get("dry_run", False)),
        refresh_config=bool(args.get("refresh_config", True)),
        skip_bootstrap=bool(args.get("skip_bootstrap", False)),
        manifest_path=args.get("manifest_path"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_org_automation_tool,
)
