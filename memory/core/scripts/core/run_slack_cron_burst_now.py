#!/usr/bin/env python3
"""Trigger every cron job with deliver=slack:*, then run one scheduler tick for those jobs only.

Patches cron.scheduler.get_due_jobs for the duration of tick() so other due jobs are not run.

Usage:
  HERMES_HOME=~/.hermes/profiles/chief-orchestrator \\
    ./venv/bin/python scripts/core/run_slack_cron_burst_now.py [--no-dedupe]

``--no-dedupe`` sets ``HERMES_CRON_DELIVERY_DEDUPE=0`` so repeat check-ins are not skipped
when body fingerprints match the last successful delivery.
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable cron delivery fingerprint dedupe for this run (test / forced check-ins).",
    )
    args = ap.parse_args()
    if args.no_dedupe:
        os.environ["HERMES_CRON_DELIVERY_DEDUPE"] = "0"

    hh = os.environ.get("HERMES_HOME", "").strip()
    if not hh:
        print("Set HERMES_HOME to the active profile directory.", file=sys.stderr)
        return 2
    os.environ["HERMES_HOME"] = os.path.expanduser(hh)

    repo = os.path.expanduser("~/hermes-agent")
    if repo not in sys.path:
        sys.path.insert(0, repo)

    from cron.jobs import load_jobs, trigger_job
    import cron.scheduler as sch

    slack_ids = [j["id"] for j in load_jobs() if str(j.get("deliver", "")).startswith("slack:")]
    if not slack_ids:
        print("No slack:* deliver cron jobs in this profile.", file=sys.stderr)
        return 1

    print(f"Triggering {len(slack_ids)} slack cron job(s)", file=sys.stderr)
    for jid in slack_ids:
        trigger_job(jid)

    _orig = sch.get_due_jobs
    slack_set = frozenset(slack_ids)

    def _slack_due():
        return [j for j in _orig() if j["id"] in slack_set]

    sch.get_due_jobs = _slack_due
    try:
        total = 0
        # tick() may return 0 if another process holds ~/.hermes/.../cron/.tick.lock (e.g. gateway).
        for attempt in range(60):
            n = sch.tick(verbose=True)
            total += n
            if n > 0:
                print(f"tick executed {n} job(s) (attempt {attempt + 1})", file=sys.stderr)
                break
            due = _slack_due()
            if not due:
                print("No slack jobs remain due after tick — done or already advanced.", file=sys.stderr)
                break
            time.sleep(5)
        else:
            print("Gave up waiting for cron tick lock (gateway may hold it).", file=sys.stderr)
            return 3
    finally:
        sch.get_due_jobs = _orig
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
