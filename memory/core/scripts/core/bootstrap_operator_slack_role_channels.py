#!/usr/bin/env python3
"""Join/create operator-workspace Slack channels, write messaging_role_routing.yaml, extend allowlist, run sync.

Expects HERMES_HOME (e.g. ~/.hermes/profiles/chief-orchestrator), repo checkout with venv at ~/hermes-agent.
Run on the operator Mac (or via ssh_operator.sh) after deploying updated sync_slack_role_cron_jobs.py.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _api(tok: str, method: str, **params: str) -> dict:
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _channels_by_name(tok: str) -> dict[str, str]:
    """Slack channel name -> id (public + private; paginated)."""
    by_name: dict[str, str] = {}
    cursor = ""
    for _ in range(80):
        params: dict[str, str] = {"types": "public_channel,private_channel", "limit": "200"}
        if cursor:
            params["cursor"] = cursor
        r = _api(tok, "conversations.list", **params)
        if not r.get("ok"):
            print(f"conversations.list: {r}", file=sys.stderr)
            break
        for c in r.get("channels") or []:
            nm = (c.get("name") or "").strip()
            cid = (c.get("id") or "").strip()
            if nm and cid:
                by_name.setdefault(nm, cid)
        cursor = ((r.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    return by_name


def _first_channel_id(by_name: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        cid = by_name.get(n)
        if cid:
            return cid
    return None


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--skip-burst",
        action="store_true",
        help="After sync/filter, do not run run_slack_cron_burst_now (use when chaining "
        "sync --refresh-prompts / --policy-checkin and archived channels would make the smoke burst exit 1).",
    )
    args = ap.parse_args()

    hh = (os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME to the chief-orchestrator profile directory.", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    _load_dotenv(home / ".env")
    tok = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if not tok:
        print("SLACK_BOT_TOKEN missing from profile .env", file=sys.stderr)
        return 2

    by_name = _channels_by_name(tok)

    join_ids = [
        "C0ARW3DANGP",  # dept-engineering
        "C0AS9ETE1D4",  # dept-operations
        "C0ASBGRM1H8",  # dept-product
    ]

    for cid in join_ids:
        ua = _api(tok, "conversations.unarchive", channel=cid)
        if ua.get("ok"):
            print(f"unarchived {cid}")
        elif ua.get("error") not in ("not_archived", "channel_not_found"):
            print(f"conversations.unarchive {cid}: {ua}", file=sys.stderr)
        r = _api(tok, "conversations.join", channel=cid)
        if not r.get("ok"):
            print(f"conversations.join {cid}: {r}", file=sys.stderr)
        else:
            print(f"joined {cid}")

    hr_id = None
    cr = _api(tok, "conversations.create", name="dept-org-mapper-hr", is_private="false")
    if cr.get("ok") and cr.get("channel", {}).get("id"):
        hr_id = cr["channel"]["id"]
        print(f"created dept-org-mapper-hr -> {hr_id}")
    else:
        print(f"conversations.create dept-org-mapper-hr: {cr} — trying list", file=sys.stderr)
        lst = _api(tok, "conversations.list", types="public_channel", limit="800")
        for c in lst.get("channels") or []:
            if c.get("name") == "dept-org-mapper-hr":
                hr_id = c.get("id")
                print(f"found existing dept-org-mapper-hr -> {hr_id}")
                break
    if not hr_id:
        hr_id = by_name.get("dept-org-mapper-hr") or ""
    if not hr_id:
        print(
            "WARN: could not resolve dept-org-mapper-hr channel — org-mapper-hr-controller not added",
            file=sys.stderr,
        )

    channels_map: dict[str, str] = {
        "C0ASBRNU9QA": "chief_orchestrator",
        "C0ASBRP407L": "chief_orchestrator",
        "C0AS8DNN353": "chief_orchestrator",
        # #org-registry — must not use chief_orchestrator or sync skips role cron for this channel
        "C0ASQNGCLV7": "org-registry-coordinator",
        "C0ARW3DANGP": "engineering-director",
        "C0AS9ET6X2A": "it-security-director",
        "C0AS9ETE1D4": "operations-director",
        "C0ASBGRM1H8": "product-director",
        "C0ARWCARRF1": "project-lead-agentic-company",
    }
    optional_channels = (
        (
            ("risk-and-incidents", "risk-and-incident", "risk-and-incents", "risk-and-insights"),
            "risk-and-insights-director",
        ),
        (("org-registry",), "org-registry-coordinator"),
        (("executive-briefing", "executive-briefings"), "executive-briefing-lead"),
    )
    for names, role in optional_channels:
        cid = _first_channel_id(by_name, names)
        if cid:
            channels_map[cid] = role

    if hr_id:
        channels_map[hr_id] = "org-mapper-hr-controller"

    join_extra = [cid for cid in channels_map if cid.startswith("C") and cid not in join_ids]
    for cid in join_extra:
        ua = _api(tok, "conversations.unarchive", channel=cid)
        if ua.get("ok"):
            print(f"unarchived {cid}")
        elif ua.get("error") not in ("not_archived", "channel_not_found"):
            print(f"conversations.unarchive {cid}: {ua}", file=sys.stderr)
        r = _api(tok, "conversations.join", channel=cid)
        if not r.get("ok"):
            print(f"conversations.join {cid}: {r}", file=sys.stderr)
        else:
            print(f"joined {cid}")

    chan_lines = "\n".join(f"      {cid}: {role}" for cid, role in sorted(channels_map.items()))
    channels_yaml = f"""# Operator Slack workspace — role_routing for gateway + Slack role cron sync.
# Regenerated by bootstrap_operator_slack_role_channels.py

role_routing:
  enabled: true
  default_role: chief_orchestrator
  slack:
    channels:
{chan_lines}
    threads: {{}}
"""

    ops = home / "workspace" / "memory" / "runtime" / "operations"
    ops.mkdir(parents=True, exist_ok=True)
    overlay_path = ops / "messaging_role_routing.yaml"
    overlay_path.write_text(channels_yaml, encoding="utf-8")
    print(f"wrote {overlay_path}")

    # Merge SLACK_ALLOWED_CHANNELS
    env_path = home / ".env"
    text = env_path.read_text(encoding="utf-8", errors="replace") if env_path.is_file() else ""
    need = set(channels_map.keys())
    cur: set[str] = set()
    export_prefix = ""
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^(export\s+)?SLACK_ALLOWED_CHANNELS=(.*)$", s)
        if not m:
            continue
        if m.group(1):
            export_prefix = "export "
        for part in m.group(2).strip().strip('"').strip("'").split(","):
            p = part.strip()
            if p:
                cur.add(p)
    merged = cur | need
    new_line = f'{export_prefix}SLACK_ALLOWED_CHANNELS={",".join(sorted(merged))}'
    lines_out: list[str] = []
    replaced = False
    for line in text.splitlines():
        if re.match(r"^[ \t]*(?:export[ \t]+)?SLACK_ALLOWED_CHANNELS=", line):
            lines_out.append(new_line)
            replaced = True
        else:
            lines_out.append(line)
    if not replaced:
        if lines_out and lines_out[-1].strip():
            lines_out.append("")
        lines_out.append(new_line)
    text2 = "\n".join(lines_out) + ("\n" if text.endswith("\n") or not text else "")
    env_path.write_text(text2, encoding="utf-8")
    print(f"updated SLACK_ALLOWED_CHANNELS ({len(merged)} ids) in {env_path}")

    repo = Path.home() / "hermes-agent"
    py = repo / "venv" / "bin" / "python"
    sync = repo / "memory" / "core" / "scripts" / "core" / "sync_slack_role_cron_jobs.py"
    filt = repo / "memory" / "core" / "scripts" / "core" / "filter_role_routing_slack_by_env.py"
    burst = repo / "memory" / "core" / "scripts" / "core" / "run_slack_cron_burst_now.py"
    env = {**os.environ, "HERMES_HOME": str(home)}
    r = subprocess.run([str(py), str(sync), "--apply"], cwd=str(repo), env=env)
    if r.returncode != 0:
        return r.returncode
    r = subprocess.run([str(py), str(filt)], cwd=str(repo), env=env)
    if r.returncode != 0:
        print("filter_role_routing_slack_by_env failed (non-fatal if allowlist already superset)", file=sys.stderr)
    if args.skip_burst:
        return 0
    env["HERMES_CRON_DELIVERY_DEDUPE"] = "0"
    r = subprocess.run([str(py), str(burst), "--ping-job-prompt"], cwd=str(repo), env=env)
    if r.returncode != 0:
        return r.returncode
    if os.environ.get("HERMES_SLACK_BOOTSTRAP_LLM_BURST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        r = subprocess.run([str(py), str(burst), "--no-dedupe"], cwd=str(repo), env=env)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
