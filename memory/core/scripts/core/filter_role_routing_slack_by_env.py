#!/usr/bin/env python3
"""Restrict ``messaging.role_routing.slack.channels`` to IDs allowlisted in this profile's ``.env``.

Reads ``SLACK_ALLOWED_CHANNELS`` (comma-separated). Optionally includes ``SLACK_HOME_CHANNEL``
(DM id) when set, so home/cron targets stay consistent.

If ``workspace/memory/runtime/operations/messaging_role_routing.yaml`` exists and defines
``role_routing.slack.channels``, filters that mapping the same way (overlay replaces merged
channels in the gateway loader).

Does not modify Slack tokens — only routing maps. Run on **each** host for its own profile.

Usage:
  HERMES_HOME=~/.hermes/profiles/chief-orchestrator-droplet \\
    ./venv/bin/python scripts/core/filter_role_routing_slack_by_env.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
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


def _parse_env_channels(env_path: Path) -> set[str]:
    text = env_path.read_text(encoding="utf-8", errors="replace") if env_path.is_file() else ""
    allow: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?(SLACK_ALLOWED_CHANNELS|SLACK_HOME_CHANNEL)=(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if key == "SLACK_ALLOWED_CHANNELS":
            for part in val.split(","):
                cid = part.strip()
                if cid:
                    allow.add(cid)
        elif key == "SLACK_HOME_CHANNEL" and val:
            allow.add(val)
    return allow


def _load_yaml(p: Path) -> dict:
    import yaml

    if not p.is_file():
        return {}
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    return d if isinstance(d, dict) else {}


def _save_yaml(p: Path, data: dict) -> None:
    import yaml

    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _filter_channels(channels: dict, allow: set[str]) -> tuple[dict, list[str]]:
    if not isinstance(channels, dict):
        return {}, []
    out = {}
    dropped = []
    for cid, slug in channels.items():
        k = str(cid).strip()
        if k in allow:
            out[k] = slug
        else:
            dropped.append(k)
    return out, dropped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    hh = (os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME to the profile directory.", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    env_path = home / ".env"
    allow = _parse_env_channels(env_path)
    if not allow:
        print(f"No SLACK_ALLOWED_CHANNELS (or SLACK_HOME_CHANNEL) in {env_path}", file=sys.stderr)
        return 1
    print(f"allowlist: {len(allow)} id(s) from .env")

    cfg_path = home / "config.yaml"
    cfg = _load_yaml(cfg_path)
    msg = cfg.setdefault("messaging", {})
    rr = msg.setdefault("role_routing", {})
    slack_rr = rr.setdefault("slack", {})
    ch = slack_rr.get("channels")
    if not isinstance(ch, dict):
        ch = {}
    new_ch, dropped = _filter_channels(ch, allow)
    if dropped:
        print(f"dropped from config.yaml (not in .env allowlist): {dropped}")
    if new_ch != ch:
        slack_rr["channels"] = new_ch
        if not args.dry_run:
            _save_yaml(cfg_path, cfg)
        print(f"config.yaml: {len(ch)} -> {len(new_ch)} channel(s)")
    else:
        print("config.yaml: unchanged")

    ops = home / "workspace" / "memory" / "runtime" / "operations"
    overlay = ops / "messaging_role_routing.yaml"
    if overlay.is_file():
        doc = _load_yaml(overlay)
        rro = doc.get("role_routing") or {}
        if not isinstance(rro, dict):
            rro = {}
        slo = rro.get("slack") or {}
        if not isinstance(slo, dict):
            slo = {}
        och = slo.get("channels")
        if isinstance(och, dict) and och:
            new_och, drop_o = _filter_channels(och, allow)
            if drop_o:
                print(f"dropped from overlay (not in .env allowlist): {drop_o}")
            if new_och != och:
                slo["channels"] = new_och
                rro["slack"] = slo
                doc["role_routing"] = rro
                if not args.dry_run:
                    overlay.parent.mkdir(parents=True, exist_ok=True)
                    _save_yaml(overlay, doc)
                print(f"overlay: {len(och)} -> {len(new_och)} channel(s)")
            else:
                print("overlay: unchanged")
        else:
            print("overlay: no role_routing.slack.channels to filter")
    else:
        print("no messaging_role_routing.yaml overlay")

    if args.dry_run:
        print("dry-run — no files written")
        return 0

    # Prune cron jobs whose deliver slack:<id> is not allowlisted (avoid stale operator channels).
    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import load_jobs, save_jobs

    jobs = load_jobs()
    kept, removed = [], []
    for j in jobs:
        d = str(j.get("deliver") or "")
        if d.startswith("slack:"):
            rest = d.split(":", 1)[1]
            cid = rest.split(":", 1)[0] if rest else ""
            if cid and cid not in allow:
                removed.append((j.get("name") or j.get("id"), d))
                continue
        kept.append(j)
    if removed:
        for name, d in removed:
            print(f"remove cron job (deliver not allowlisted): {name} ({d})")
        save_jobs(kept)
    else:
        print("cron jobs: no slack deliver targets to prune")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
