#!/usr/bin/env python3
"""Repair missing next_run_at on enabled cron/interval jobs (writes profile cron/jobs.json).

Run with HERMES_HOME set to the active profile, e.g.:

  HERMES_HOME=~/.hermes/profiles/chief-orchestrator ./venv/bin/python scripts/core/repair_cron_next_run.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root: scripts/core -> repo
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if len(sys.argv) > 1:
        os.environ["HERMES_HOME"] = str(Path(sys.argv[1]).expanduser())
    elif not os.environ.get("HERMES_HOME"):
        print("Usage: HERMES_HOME=/path/to/profile python repair_cron_next_run.py", file=sys.stderr)
        print("   or: python repair_cron_next_run.py /path/to/profile", file=sys.stderr)
        return 2

    from cron.jobs import (  # noqa: E402
        _hermes_now,
        _recover_missing_next_run_at,
        load_jobs,
        save_jobs,
    )

    jobs = load_jobs()
    fixed = 0
    for j in jobs:
        if not j.get("enabled", True):
            continue
        if j.get("next_run_at"):
            continue
        sched = j.get("schedule") or {}
        kind = sched.get("kind")
        if kind not in ("cron", "interval"):
            continue
        nxt = _recover_missing_next_run_at(sched, j.get("last_run_at"), _hermes_now())
        if not nxt:
            print(f"skip {j.get('name', j.get('id'))}: could not compute next run", file=sys.stderr)
            continue
        j["next_run_at"] = nxt
        if j.get("state") == "completed" and kind in ("cron", "interval"):
            j["state"] = "scheduled"
        fixed += 1
        print(f"fixed next_run_at for {j.get('name', j.get('id'))} -> {nxt}")
    if fixed:
        save_jobs(jobs)
    else:
        print("nothing to fix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
