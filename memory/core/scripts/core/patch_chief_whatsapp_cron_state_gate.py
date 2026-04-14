#!/usr/bin/env python3
"""
Add ``state_skip_gate`` to stateful WhatsApp/monitor crons and normalize prompts.

- Operator paths: ``/Users/operator/.hermes/cron-state/...`` (override with --cron-state-root).
- WhatsApp ``deliver`` jobs: ensure OpenRouter ``openrouter/free`` and a closing
  line of ``--<hop> --chief-orchestrator`` where ``<hop>`` reflects the current host.

Run on the host that owns the profile (e.g. Mac mini):

  HERMES_HOME=~/.hermes/profiles/chief-orchestrator \\
    ./venv/bin/python scripts/core/patch_chief_whatsapp_cron_state_gate.py --apply

Dry run (default): prints planned edits only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


def _default_cron_state_root(home: Path) -> Path:
    """Infer ~/Library/... vs /Users/operator from HERMES_HOME parent."""
    return home.parent.parent / "cron-state"


def _env_file_value(home: Path, key: str) -> str:
    env_path = home / ".env"
    if not env_path.is_file():
        return ""
    pattern = re.compile(rf"^(?:export\s+)?{re.escape(key)}=(.*)$")
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pattern.match(raw.strip())
        if not m:
            continue
        return m.group(1).strip().strip('"').strip("'")
    return ""


def _infer_hermes_hop_tag(home: Path) -> str:
    env = (os.environ.get("HERMES_SLACK_ROLE_HERMES_HOP") or "").strip().lower()
    if env in ("droplet", "operator"):
        return f"--{env}"
    for key in ("HERMES_GATEWAY_LOCK_INSTANCE", "HERMES_CLI_INSTANCE_LABEL"):
        val = (os.environ.get(key) or _env_file_value(home, key)).strip().lower()
        if val in ("droplet", "operator"):
            return f"--{val}"
    try:
        if home.expanduser().resolve().name.endswith("-droplet"):
            return "--droplet"
    except OSError:
        pass
    return "--operator"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write jobs.json (default is dry run)",
    )
    ap.add_argument(
        "--cron-state-root",
        type=Path,
        help="Directory containing per-job state dirs (default: ~/.hermes/cron-state for default profile)",
    )
    args = ap.parse_args()

    hh = os.environ.get("HERMES_HOME", "").strip()
    if not hh:
        print("Set HERMES_HOME to the profile directory.", file=__import__("sys").stderr)
        return 2
    home = Path(hh).expanduser()
    root = args.cron_state_root or _default_cron_state_root(home)
    hop_tag = _infer_hermes_hop_tag(home)

    gates = {
        "6bc442ae2aec": {
            "path": str(root / "whatsapp-gateway-watchdog" / "state.json"),
            "keys": ["last_status_key", "connected_platforms"],
        },
        "cd38fdfdc932": {
            "path": str(root / "hourly-whatsapp-human-operator-escalation" / "state.json"),
            "keys": ["last_status_key"],
        },
    }

    suffix = (
        f"\n\nAppend a final line containing exactly: {hop_tag} --chief-orchestrator\n"
        "(Place it on its own line after the message content.)"
    )
    marker_prefix = "Append a final line containing exactly:"

    jobs_path = home / "cron" / "jobs.json"
    if not jobs_path.is_file():
        print(f"Missing {jobs_path}", file=__import__("sys").stderr)
        return 1

    data = json.loads(jobs_path.read_text(encoding="utf-8"))
    droplet_prefix = "/home/hermesuser/.hermes/cron-state/"

    edits = 0
    for job in data.get("jobs", []):
        jid = job.get("id")
        if jid in gates:
            if job.get("state_skip_gate") != gates[jid]:
                job["state_skip_gate"] = gates[jid]
                job.pop("last_state_gate_fingerprint", None)
                edits += 1
                print(f"state_skip_gate: {job.get('name')} ({jid})")
        d = job.get("deliver") or ""
        if str(d).startswith("whatsapp:"):
            pr = job.get("prompt") or ""
            if droplet_prefix in pr:
                updated_pr = pr.replace(droplet_prefix, str(root) + "/")
                if updated_pr != pr:
                    pr = updated_pr
                    edits += 1
                    print(f"prompt paths: {job.get('name')}")
            desired_marker = f"{marker_prefix} {hop_tag} --chief-orchestrator"
            if marker_prefix in pr and desired_marker not in pr:
                pr = re.sub(
                    r"Append a final line containing exactly:\s+--(?:operator|droplet)\s+--chief-orchestrator",
                    desired_marker,
                    pr,
                )
                job["prompt"] = pr
                edits += 1
                print(f"suffix replace: {job.get('name')}")
            elif f"{hop_tag} --chief-orchestrator" not in pr and desired_marker not in pr:
                job["prompt"] = pr.rstrip() + suffix
                edits += 1
                print(f"suffix: {job.get('name')}")
            if job.get("model") != "openrouter/free" or job.get("provider") != "openrouter":
                job["model"] = "openrouter/free"
                job["provider"] = "openrouter"
                job["base_url"] = None
                edits += 1
                print(f"model: {job.get('name')} -> openrouter/free")

    if not edits:
        print("No changes needed.")
        return 0
    if not args.apply:
        print(f"\nDry run: {edits} change(s). Pass --apply to write {jobs_path}")
        return 0

    jobs_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
