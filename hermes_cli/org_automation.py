"""Org profile bootstrap + ORG_REGISTRY / ORG_CHART sync from org_agent_profiles_manifest.

Provides ``hermes workspace org-automation apply`` and optional agent tool
``sync_org_automation`` so the chief orchestrator (or cron) can create/update
Hermes role profiles and refresh workspace markdown registers without hand-editing.

All writes are scoped to ``HERMES_HOME`` (active profile). Chief approval is still
expected via policy; this code only automates mechanical steps.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

from hermes_constants import get_hermes_home

_SYNC_BEGIN = "<!-- HERMES_ORG_MANIFEST_SYNC:BEGIN -->"
_SYNC_END = "<!-- HERMES_ORG_MANIFEST_SYNC:END -->"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ops_dir() -> Path:
    return get_hermes_home() / "workspace" / "operations"


def _load_manifest(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest (expected mapping): {path}")
    return data


def _manifest_rows(manifest: Dict[str, Any]) -> List[tuple[str, str, str]]:
    rows: List[tuple[str, str, str]] = []
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list):
        return rows
    for entry in profiles:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        ag = entry.get("ag_id")
        ag_s = str(ag).strip() if ag else "—"
        rp = entry.get("role_prompt")
        rp_s = str(rp).strip() if rp else "—"
        rows.append((name, ag_s, rp_s))
    return rows


def _render_sync_block(manifest: Dict[str, Any], manifest_path: Path) -> str:
    lines = [
        _SYNC_BEGIN,
        "",
        f"_Generated from manifest: `{manifest_path}`_",
        "",
        "| Hermes profile | AG-ID | Role prompt (repo path) |",
        "|----------------|-------|-------------------------|",
    ]
    for name, ag_s, rp_s in _manifest_rows(manifest):
        lines.append(f"| `{name}` | {ag_s} | `{rp_s}` |")
    lines.extend(
        [
            "",
            "Update the manifest in the repo, then run:",
            "`hermes workspace org-automation apply`",
            "",
            _SYNC_END,
            "",
        ]
    )
    return "\n".join(lines)


def _replace_or_append_block(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if _SYNC_BEGIN in text and _SYNC_END in text:
        pre, rest = text.split(_SYNC_BEGIN, 1)
        _, post = rest.split(_SYNC_END, 1)
        new_body = pre.rstrip() + "\n\n" + block + post.lstrip()
    else:
        sep = "\n\n" if text.strip() else ""
        new_body = text.rstrip() + sep + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_body.strip() + "\n", encoding="utf-8")


def sync_org_markdown_files(
    manifest: Dict[str, Any],
    *,
    manifest_path: Path,
    dry_run: bool,
) -> List[str]:
    """Refresh auto blocks in ORG_REGISTRY.md and ORG_CHART.md under workspace/operations."""
    ops = _ops_dir()
    log: List[str] = []
    block = _render_sync_block(manifest, manifest_path)

    for fname in ("ORG_REGISTRY.md", "ORG_CHART.md"):
        dest = ops / fname
        if dry_run:
            log.append(f"[dry-run] would update {dest}")
            continue
        if not dest.parent.is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            header = f"# {fname.replace('.md', '').replace('_', ' ')}\n\n"
            dest.write_text(header, encoding="utf-8")
            log.append(f"created {dest}")
        _replace_or_append_block(dest, block)
        log.append(f"updated {dest}")
    return log


def run_bootstrap_script(
    *,
    repo_root: Path,
    manifest: Path,
    dry_run: bool,
    refresh_config: bool,
) -> int:
    """Invoke scripts/core/bootstrap_org_agent_profiles.py in a subprocess."""
    script = repo_root / "scripts" / "core" / "bootstrap_org_agent_profiles.py"
    if not script.is_file():
        print(f"Missing {script}", file=sys.stderr)
        return 1
    py = repo_root / "venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    cmd = [str(py), str(script), "--manifest", str(manifest)]
    if dry_run:
        cmd.append("--dry-run")
    if refresh_config:
        cmd.append("--refresh-config")
    r = subprocess.run(cmd, cwd=str(repo_root), check=False)
    return int(r.returncode)


def workspace_org_automation_apply(
    *,
    dry_run: bool,
    skip_bootstrap: bool,
    refresh_config: bool,
    manifest: Path | None,
) -> int:
    repo = _repo_root()
    mpath = manifest or (repo / "scripts" / "core" / "org_agent_profiles_manifest.yaml")
    if not mpath.is_file():
        print(f"Manifest not found: {mpath}", file=sys.stderr)
        return 1

    manifest_data = _load_manifest(mpath)
    logs = sync_org_markdown_files(manifest_data, manifest_path=mpath, dry_run=dry_run)
    for ln in logs:
        print(ln)

    if skip_bootstrap:
        print("(skip-bootstrap: no profile create/merge)")
        return 0

    code = run_bootstrap_script(
        repo_root=repo,
        manifest=mpath,
        dry_run=dry_run,
        refresh_config=refresh_config,
    )
    return code


def workspace_org_automation_command(args) -> None:
    action = getattr(args, "org_automation_action", None)
    if action != "apply":
        print(
            "Usage: hermes workspace org-automation apply [--dry-run] [--skip-bootstrap] "
            "[--refresh-config] [--manifest PATH]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    dry_run = bool(getattr(args, "dry_run", False))
    skip = bool(getattr(args, "skip_bootstrap", False))
    refresh = bool(getattr(args, "refresh_config", False))
    mp = getattr(args, "manifest", None)
    manifest_path = Path(mp).expanduser() if mp else None
    code = workspace_org_automation_apply(
        dry_run=dry_run,
        skip_bootstrap=skip,
        refresh_config=refresh,
        manifest=manifest_path,
    )
    raise SystemExit(code)


def sync_org_automation_tool(
    *,
    dry_run: bool = False,
    refresh_config: bool = True,
    skip_bootstrap: bool = False,
    manifest_path: str | None = None,
) -> str:
    """JSON result for ``sync_org_automation`` tool (agent-callable)."""
    import json

    repo = _repo_root()
    mp = Path(manifest_path).expanduser() if manifest_path else None
    try:
        code = workspace_org_automation_apply(
            dry_run=dry_run,
            skip_bootstrap=skip_bootstrap,
            refresh_config=refresh_config,
            manifest=mp,
        )
        return json.dumps(
            {
                "success": code == 0,
                "exit_code": code,
                "hermes_home": str(get_hermes_home()),
                "dry_run": dry_run,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
