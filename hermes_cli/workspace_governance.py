"""CLI helpers for workspace/operations governance files."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from hermes_constants import display_hermes_home, get_hermes_home


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ops_dir() -> Path:
    return get_hermes_home() / "workspace" / "operations"


def _templates() -> tuple[Path, Path, Path]:
    root = _repo_root()
    return (
        root / "scripts" / "templates" / "runtime_governance.runtime.example.yaml",
        root / "scripts" / "templates" / "role_assignments.example.yaml",
        root / "scripts" / "templates" / "messaging_channel_role_map.example.yaml",
    )


def cmd_workspace_governance_init(_args) -> None:
    ops = _ops_dir()
    ops.mkdir(parents=True, exist_ok=True)
    gov, roles, chmap = _templates()
    for src, name in (
        (gov, "runtime_governance.runtime.yaml"),
        (roles, "role_assignments.yaml"),
        (chmap, "messaging_channel_role_map.yaml"),
    ):
        dest = ops / name
        if dest.exists():
            print(f"Exists (skip): {dest}")
            continue
        if not src.is_file():
            print(f"Missing template: {src}", file=sys.stderr)
            sys.exit(1)
        shutil.copyfile(src, dest)
        print(f"Created {dest}")
    print(f"\nOperations directory: {display_hermes_home()}/workspace/operations/")
    print("Edit the .yaml files, then restart gateway / open a new CLI session.")


def cmd_workspace_governance_show(_args) -> None:
    path = get_hermes_home() / "workspace" / "operations" / "runtime_governance.runtime.yaml"
    if not path.is_file():
        print(f"No file at {path} — run: hermes workspace governance init")
        return
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not parse YAML: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(doc, dict):
        print("Invalid document (expected mapping).", file=sys.stderr)
        sys.exit(1)
    # Redact nothing today — file should not contain secrets; avoid dumping huge values
    safe = {k: v for k, v in doc.items() if k in (
        "version", "enabled", "activation_session", "active_role_slug", "assigned_role",
        "assigned_by", "summary", "directives", "concise_directives", "read_order_paths",
        "policy_reads", "notes",
    )}
    print(yaml.dump(safe, default_flow_style=False, allow_unicode=True))


def cmd_workspace_governance_paths(_args) -> None:
    home = get_hermes_home()
    print(f"runtime_governance:       {home / 'workspace' / 'operations' / 'runtime_governance.runtime.yaml'}")
    print(f"role_assignments:         {home / 'workspace' / 'operations' / 'role_assignments.yaml'}")
    print(f"messaging_channel_role_map: {home / 'workspace' / 'operations' / 'messaging_channel_role_map.yaml'}")
    print(f"messaging_role_routing:     {home / 'workspace' / 'operations' / 'messaging_role_routing.yaml'}")


def cmd_workspace_governance_sync_messaging(_args) -> None:
    script = _repo_root() / "scripts" / "core" / "sync_messaging_governance.py"
    if not script.is_file():
        print(f"Missing {script}", file=sys.stderr)
        sys.exit(1)
    r = subprocess.run([sys.executable, str(script)], check=False)
    raise SystemExit(r.returncode)


def workspace_governance_command(args) -> None:
    action = getattr(args, "governance_action", None)
    if action == "init":
        cmd_workspace_governance_init(args)
    elif action == "show":
        cmd_workspace_governance_show(args)
    elif action == "path":
        cmd_workspace_governance_paths(args)
    elif action == "sync-messaging":
        cmd_workspace_governance_sync_messaging(args)
    else:
        print(
            "Usage: hermes workspace governance {init|show|path|sync-messaging}",
            file=sys.stderr,
        )
        sys.exit(2)
