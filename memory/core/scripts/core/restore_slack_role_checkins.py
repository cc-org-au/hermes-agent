#!/usr/bin/env python3
"""Re-enable Slack gateway + Slack role-cron leader for this profile.

Use on **operator** or **droplet** when each machine has its **own** Slack app tokens
(different `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` in this profile's `.env`) and its own
`messaging.role_routing.slack.channels` in `config.yaml` (or workspace overlay).

This reverses the ``isolate_droplet_orchestrator`` defaults that disabled Slack on the VPS.

After running, execute (same profile):

  HERMES_HOME=... ./venv/bin/python scripts/core/repair_cron_next_run.py
  HERMES_HOME=... ./venv/bin/python scripts/core/realign_chief_cron_schedules.py
  HERMES_HOME=... ./venv/bin/python memory/core/scripts/core/sync_slack_role_cron_jobs.py --apply [--hermes-hop auto|droplet|operator]

Then ``gateway restart --sync``.

Or pass ``--run-sync`` to invoke sync_slack_role_cron_jobs (optional ``--hermes-hop``; default ``auto`` → closing line uses ``--operator``; pass ``droplet`` only if prompts must name the VPS hop).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for anc in [p.parent, *p.parents]:
        if (anc / "cron" / "jobs.py").is_file():
            return anc
    return p.parents[4]


ROOT = _repo_root()
sys.path.insert(0, str(ROOT))


def _load_yaml(path: Path) -> dict:
    import yaml

    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _save_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", metavar="PATH", help="Profile dir (default: HERMES_HOME)")
    ap.add_argument(
        "--hermes-hop",
        choices=("auto", "droplet", "operator"),
        default="auto",
        help="Passed to sync_slack_role_cron_jobs when --run-sync (default auto → --operator in prompts)",
    )
    ap.add_argument(
        "--chief-tag",
        default=None,
        metavar="STRING",
        help="Deprecated: forwarded to sync as --chief-tag if set (prefer --hermes-hop)",
    )
    ap.add_argument(
        "--run-sync",
        action="store_true",
        help="Run sync_slack_role_cron_jobs.py --apply after patching config",
    )
    args = ap.parse_args()

    hh = (args.home or os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME or --home", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    if not home.is_dir():
        print(f"Not a directory: {home}", file=sys.stderr)
        return 2

    cfg_path = home / "config.yaml"
    cfg = _load_yaml(cfg_path)
    plat = cfg.setdefault("platforms", {})
    if not isinstance(plat, dict):
        plat = {}
        cfg["platforms"] = plat
    slack = plat.setdefault("slack", {})
    if not isinstance(slack, dict):
        slack = {}
        plat["slack"] = slack
    slack["enabled"] = True

    msg = cfg.setdefault("messaging", {})
    if not isinstance(msg, dict):
        msg = {}
        cfg["messaging"] = msg
    msg["slack_role_cron_leader"] = True

    _save_yaml(cfg_path, cfg)
    print(f"patched {cfg_path}: platforms.slack.enabled=true, messaging.slack_role_cron_leader=true")

    if args.run_sync:
        sync = ROOT / "scripts" / "core" / "sync_slack_role_cron_jobs.py"
        if not sync.is_file():
            sync = Path(__file__).resolve().parent / "sync_slack_role_cron_jobs.py"
        env = {**os.environ, "HERMES_HOME": str(home)}
        cmd = [sys.executable, str(sync), "--apply", "--hermes-hop", args.hermes_hop]
        if args.chief_tag:
            cmd.extend(["--chief-tag", args.chief_tag])
        r = subprocess.run(cmd, env=env, cwd=str(ROOT))
        return r.returncode
    print("Next: repair_cron_next_run.py, realign_chief_cron_schedules.py, sync_slack_role_cron_jobs.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
