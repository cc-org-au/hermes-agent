#!/usr/bin/env python3
"""Create per-Slack-channel daily status cron jobs from messaging.role_routing (chief profile).

- Skips channels already covered by an existing job with the same deliver target.
- Stagger minutes starting at base (default 10:05 Sydney wall time via cron minute/hour fields).
- Prompts enforce [SILENT] when no state change and forbid cross-channel duplication.

Usage:
  HERMES_HOME=~/.hermes/profiles/chief-orchestrator \\
    ./venv/bin/python scripts/core/sync_slack_role_cron_jobs.py [--apply]

Without --apply, prints planned jobs only.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_yaml(path: Path):
    import yaml

    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _role_prompt(role_slug: str, channel_id: str, *, chief_tag: str) -> str:
    return f"""Use Australia/Sydney (Hermes timezone). Run once per day at the scheduled wall time.

You are generating the **Slack-only daily status** for role `{role_slug}` in channel `{channel_id}`.

**Hard rules**
- If there is **no material change** in reportable work, risks, or decisions since the last update for this channel, respond with exactly `[SILENT]` and nothing else.
- **Never** paste or paraphrase content meant for WhatsApp connectivity alerts, Telegram project topics, other Slack channels, or the chief DM summary.
- Each channel must add **unique** information for this role remit; do not broadcast the same narrative to multiple channels.

**Content** (only when not silent)
- Lead with a compact status headline, then bullets: what changed, blockers, next 24h.
- Align with published policies under `HERMES_HOME/policies/` relevant to `{role_slug}` when applicable (do not paste large policy text).

**Closing**
Append its own final line exactly: `{chief_tag} --{role_slug}`"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write jobs.json")
    parser.add_argument("--base-hour", type=int, default=10, help="Local hour for first stagger (default 10)")
    parser.add_argument(
        "--base-minute",
        type=int,
        default=10,
        help="First minute slot (default 10 — after chief 10:05 summary / lead 10:01 on typical layouts)",
    )
    parser.add_argument("--stagger", type=int, default=2, help="Minutes between channels (default 2)")
    parser.add_argument(
        "--chief-tag",
        default="--operator --chief-orchestrator",
        help="Trailing signature line for org consistency",
    )
    args = parser.parse_args()

    hh = os.environ.get("HERMES_HOME", "").strip()
    if not hh:
        print("Set HERMES_HOME to the profile directory (e.g. ~/.hermes/profiles/chief-orchestrator).", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    cfg = _load_yaml(home / "config.yaml")
    rr = (cfg.get("messaging") or {}).get("role_routing") or {}
    slack = (rr.get("slack") or {}).get("channels") or {}
    if not isinstance(slack, dict) or not slack:
        print("No messaging.role_routing.slack.channels in config.yaml — nothing to do", file=sys.stderr)
        return 1

    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import compute_next_run, load_jobs, save_jobs

    jobs = load_jobs()
    existing_deliver = {str(j.get("deliver", "")) for j in jobs}

    minute = args.base_minute
    planned = []
    for channel_id, role_slug in sorted(slack.items(), key=lambda x: x[1]):
        cid = str(channel_id).strip()
        slug = str(role_slug).strip()
        if slug == "chief_orchestrator":
            print(f"skip chief_orchestrator channel {cid} (dedicated chief summary / operator DM jobs cover orchestration)")
            continue
        deliver = f"slack:{cid}"
        name = f"daily-slack-role-status-{slug}-{cid}"
        if deliver in existing_deliver:
            print(f"skip (exists): {deliver}")
            continue
        expr = f"{minute} {args.base_hour} * * *"
        minute += args.stagger
        prompt = _role_prompt(slug, cid, chief_tag=args.chief_tag)
        job = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "prompt": prompt,
            "skills": [],
            "skill": None,
            "model": None,
            "provider": None,
            "base_url": None,
            "schedule": {"kind": "cron", "expr": expr, "display": expr},
            "schedule_display": expr,
            "repeat": {"times": 999999, "completed": 0},
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "created_at": __import__("datetime").datetime.now().astimezone().isoformat(),
            "next_run_at": compute_next_run({"kind": "cron", "expr": expr}),
            "last_run_at": None,
            "last_status": None,
            "last_error": None,
            "deliver": deliver,
            "origin": None,
        }
        planned.append(job)
        print(f"plan: {name} {expr} -> {deliver}")

    if not args.apply:
        print("\nDry run. Pass --apply to append to cron/jobs.json")
        return 0

    jobs.extend(planned)
    save_jobs(jobs)
    print(f"Wrote {len(planned)} job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
