#!/usr/bin/env python3
"""Strip Slack-target cron jobs from profiles that must not own Slack role check-ins.

Use when **two Hermes profiles** on different machines (or the same VPS) must **not** both post
to the same Slack channels:

- **Operator Mac** — ``chief-orchestrator``: keep ``messaging.slack_role_cron_leader: true`` (default)
  and the Slack role jobs created by ``sync_slack_role_cron_jobs.py --apply``.
- **VPS** — a dedicated droplet Slack-leader profile (if you intentionally maintain one):
  after ``restore_slack_role_checkins.py``, that profile owns Slack role jobs for **that** host's
  tokens and channel map.
- **VPS** — ``chief-orchestrator`` (clone left on the droplet): set
  ``messaging.slack_role_cron_leader: false`` and run this script with ``--apply`` so duplicate
  ``slack:`` cron jobs are removed (same pattern as ``isolate_droplet_orchestrator._strip_slack_cron_jobs``).

Disjoint ``SLACK_ALLOWED_CHANNELS`` / ``messaging_role_routing.yaml`` per profile ensures
``sync_slack_role_cron_jobs`` does not recreate overlapping ``deliver`` targets.

Usage:
  HERMES_HOME=~/.hermes/profiles/chief-orchestrator \\
    ./venv/bin/python memory/core/scripts/core/prune_slack_cron_for_non_leader.py --dry-run

  HERMES_HOME=... ./venv/bin/python .../prune_slack_cron_for_non_leader.py --apply [--also-set-non-leader]

``--force`` prunes even when ``slack_role_cron_leader`` is not false (dangerous on the real leader).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for anc in [p.parent, *p.parents]:
        if (anc / "cron" / "jobs.py").is_file():
            return anc
    return p.parents[4]


sys.path.insert(0, str(_repo_root()))


def _load_yaml(path: Path) -> dict:
    import yaml

    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _save_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _is_slack_cron_job(job: dict) -> bool:
    deliver = str(job.get("deliver") or "")
    name = str(job.get("name") or "")
    return deliver.startswith("slack:") or name.startswith("daily-slack-role-status-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", metavar="PATH", help="Profile dir (default: HERMES_HOME)")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--apply", action="store_true", help="Write jobs.json (and optionally config)")
    ap.add_argument(
        "--also-set-non-leader",
        action="store_true",
        help="Set messaging.slack_role_cron_leader: false in config.yaml (with --apply)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Prune even if slack_role_cron_leader is not false (do not use on the Mac leader)",
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
    msg = cfg.get("messaging") if isinstance(cfg.get("messaging"), dict) else {}
    leader_false = msg.get("slack_role_cron_leader") is False

    may_strip_via_config = bool(args.also_set_non_leader and (args.apply or args.dry_run))
    if not leader_false and not args.force and not may_strip_via_config:
        print(
            "messaging.slack_role_cron_leader is not false — refusing to prune (avoids wiping the Mac leader). "
            "Pass --apply --also-set-non-leader to demote this profile and strip jobs, or --force if you are sure.",
            file=sys.stderr,
        )
        return 3

    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import load_jobs, save_jobs

    jobs = load_jobs()
    kept: list[dict] = []
    removed: list[tuple[str, str]] = []
    for j in jobs:
        if _is_slack_cron_job(j):
            removed.append((str(j.get("name") or j.get("id")), str(j.get("deliver") or "")))
            continue
        kept.append(j)

    for name, deliver in removed:
        print(f"remove: {name} ({deliver})")
    print(f"summary: {len(removed)} remove, {len(kept)} keep (was {len(jobs)})")

    if args.dry_run:
        if args.also_set_non_leader:
            print("dry-run: would set messaging.slack_role_cron_leader: false")
        return 0

    if not args.apply:
        print("pass --apply to write files, or use --dry-run to preview", file=sys.stderr)
        return 0

    if args.also_set_non_leader:
        m = cfg.setdefault("messaging", {})
        if not isinstance(m, dict):
            m = {}
            cfg["messaging"] = m
        m["slack_role_cron_leader"] = False
        _save_yaml(cfg_path, cfg)
        print("wrote config: messaging.slack_role_cron_leader: false")

    if removed:
        save_jobs(kept)
        print(f"wrote cron/jobs.json ({len(kept)} jobs)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
