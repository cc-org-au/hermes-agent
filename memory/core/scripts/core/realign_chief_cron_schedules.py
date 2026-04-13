#!/usr/bin/env python3
"""Adjust known chief-orchestrator cron job schedules + re-enable disabled jobs.

Requires HERMES_HOME pointing at the profile. Safe to re-run: only touches listed names.

Default: move daily human-facing reports into the 10:00 Sydney hour (staggered),
keep high-frequency monitors on their existing cadence unless listed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# Cron expr uses Hermes local wall time (config timezone / HERMES_TIMEZONE).
SCHEDULE_BY_NAME = {
    "daily-lead-status-prompts-sydney": "1 10 * * *",
    "daily-chief-summary-to-operator-sydney": "5 10 * * *",
    "hourly-security-patrol-and-escalation": "33 10 * * *",
    "daily-telegram-project-status-agentic-company": "40 10 * * *",
}

RE_ENABLE_NAMES = (
    "daily-telegram-project-status-agentic-company",
    "whatsapp-gateway-connectivity-alerts",
)


def main() -> int:
    if not os.environ.get("HERMES_HOME"):
        print("HERMES_HOME must be set to the chief profile path.", file=sys.stderr)
        return 2
    from cron.jobs import compute_next_run, load_jobs, parse_schedule, save_jobs

    jobs = load_jobs()
    touched = 0
    for j in jobs:
        name = j.get("name") or ""
        if name in SCHEDULE_BY_NAME:
            expr = SCHEDULE_BY_NAME[name]
            parsed = parse_schedule(expr)
            j["schedule"] = parsed
            j["schedule_display"] = expr
            j["next_run_at"] = compute_next_run(parsed, j.get("last_run_at"))
            if j.get("state") == "completed" and parsed.get("kind") in ("cron", "interval"):
                j["state"] = "scheduled"
            j["enabled"] = True
            touched += 1
            print(f"schedule {name} -> {expr}")
        if name in RE_ENABLE_NAMES:
            if not j.get("enabled", True):
                j["enabled"] = True
                j["state"] = "scheduled"
                j["next_run_at"] = compute_next_run(j["schedule"], j.get("last_run_at"))
                touched += 1
                print(f"re-enabled {name}")
    if touched:
        save_jobs(jobs)
    else:
        print("no matching jobs updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
