#!/usr/bin/env python3
"""Repair Slack role routing for the active profile from the current workspace state.

Why this exists:
- operator and droplet can drift independently
- archived channels should not stay in role cron routing
- stale/wrong role mappings (for example org-registry or executive channels mapped to the wrong slug)
  should be rebuilt from channel names, not left in config forever

What it does:
1. Load the active profile's Slack token from `.env`
2. Fetch current Slack channels (public + private)
3. Create `dept-org-mapper-hr` if missing
4. Rebuild the managed Slack role-channel map from canonical channel names
5. Preserve any active non-managed existing mappings (for example `chief_orchestrator`)
6. Write `workspace/memory/runtime/operations/messaging_role_routing.yaml`
7. Remove stale managed channel IDs from `SLACK_ALLOWED_CHANNELS`
8. Remove all derived `daily-slack-role-status-*` cron jobs so `sync_slack_role_cron_jobs.py --apply`
   can recreate them from the repaired routing map
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for anc in [p.parent, *p.parents]:
        if (anc / "cron" / "jobs.py").is_file():
            return anc
    return p.parents[4]


ROOT = _repo_root()
sys.path.insert(0, str(ROOT))


MANAGED_ROLE_GROUPS: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("dept-engineering",), "engineering-director", None),
    (("dept-it-security",), "it-security-director", None),
    (("dept-operations",), "operations-director", None),
    (("dept-product",), "product-director", None),
    (("dept-org-mapper-hr",), "org-mapper-hr-controller", "dept-org-mapper-hr"),
    (("project-agentic-company-lead",), "project-lead-agentic-company", None),
    (
        ("risk-and-incidents", "risk-and-insights", "risk-and-incents"),
        "risk-and-insights-director",
        None,
    ),
    (("org-registry",), "org-registry-coordinator", None),
    (("executive-briefings", "executive-briefing"), "executive-team-briefings", None),
)


def _load_yaml(path: Path) -> dict:
    import yaml

    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _save_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _load_slack_env(home: Path) -> str:
    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=home)
    tok = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if not tok:
        raise SystemExit(f"SLACK_BOT_TOKEN missing for {home}")
    return tok


def _slack_api(tok: str, method: str, **params: str) -> dict:
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


def _channels_by_name(tok: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    cursor = ""
    for _ in range(80):
        params: dict[str, str] = {"types": "public_channel,private_channel", "limit": "200"}
        if cursor:
            params["cursor"] = cursor
        out = _slack_api(tok, "conversations.list", **params)
        if not out.get("ok"):
            raise RuntimeError(f"conversations.list failed: {out}")
        for ch in out.get("channels") or []:
            name = str(ch.get("name") or "").strip()
            if not name:
                continue
            rows[name] = {
                "id": str(ch.get("id") or "").strip(),
                "name": name,
                "is_archived": bool(ch.get("is_archived")),
                "is_member": bool(ch.get("is_member")),
            }
        cursor = ((out.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    return rows


def _ensure_channel(tok: str, by_name: dict[str, dict], channel_name: str) -> dict | None:
    hit = by_name.get(channel_name)
    if hit:
        return hit
    out = _slack_api(tok, "conversations.create", name=channel_name, is_private="false")
    if out.get("ok"):
        ch = out.get("channel") or {}
        row = {
            "id": str(ch.get("id") or "").strip(),
            "name": str(ch.get("name") or channel_name).strip(),
            "is_archived": bool(ch.get("is_archived")),
            "is_member": bool(ch.get("is_member", True)),
        }
        by_name[row["name"]] = row
        return row
    if out.get("error") == "name_taken":
        by_name2 = _channels_by_name(tok)
        by_name.update(by_name2)
        return by_name.get(channel_name)
    return None


def _join_if_possible(tok: str, row: dict) -> dict:
    cid = str(row.get("id") or "").strip()
    if not cid or row.get("is_archived"):
        return row
    out = _slack_api(tok, "conversations.join", channel=cid)
    if out.get("ok"):
        row = dict(row)
        row["is_member"] = True
    return row


def _current_merged_slack_channels(home: Path) -> dict[str, str]:
    from gateway.config import _extract_role_routing_overlay_doc, _merge_role_routing_overlay
    from hermes_constants import resolve_workspace_operations_dir

    cfg = _load_yaml(home / "config.yaml")
    base_rr = (cfg.get("messaging") or {}).get("role_routing") or {}
    if not isinstance(base_rr, dict):
        base_rr = {}
    overlay_path = resolve_workspace_operations_dir(home) / "messaging_role_routing.yaml"
    if not overlay_path.is_file():
        merged_rr = base_rr
    else:
        ov_doc = _load_yaml(overlay_path)
        ov_rr = _extract_role_routing_overlay_doc(ov_doc) if isinstance(ov_doc, dict) else None
        if isinstance(ov_rr, dict) and ov_rr:
            merged_rr = _merge_role_routing_overlay(dict(base_rr), dict(ov_rr))
        else:
            merged_rr = base_rr
    slack = (merged_rr.get("slack") or {}).get("channels") or {}
    return slack if isinstance(slack, dict) else {}


def _write_overlay(home: Path, channels_map: dict[str, str]) -> Path:
    from gateway.config import _extract_role_routing_overlay_doc
    from hermes_constants import resolve_workspace_operations_dir

    ops = resolve_workspace_operations_dir(home)
    overlay = ops / "messaging_role_routing.yaml"
    doc = _load_yaml(overlay)
    rr = _extract_role_routing_overlay_doc(doc) if isinstance(doc, dict) else None
    if not isinstance(rr, dict):
        rr = {}
    slack = rr.get("slack")
    if not isinstance(slack, dict):
        slack = {}
    slack["channels"] = channels_map
    slack["threads"] = {}
    rr["enabled"] = True
    rr["default_role"] = rr.get("default_role") or "chief_orchestrator"
    rr["slack"] = slack
    for k in (
        "enabled",
        "default_role",
        "default_slug",
        "slack",
        "telegram",
        "whatsapp",
        "discord",
        "signal",
        "mattermost",
        "matrix",
        "feishu",
        "wecom",
    ):
        if k in doc and k != "role_routing":
            doc.pop(k, None)
    doc["role_routing"] = rr
    overlay.parent.mkdir(parents=True, exist_ok=True)
    _save_yaml(overlay, doc)
    return overlay


def _update_allowlist(home: Path, keep_ids: set[str], stale_ids: set[str]) -> Path:
    env_path = home / ".env"
    text = env_path.read_text(encoding="utf-8", errors="replace") if env_path.is_file() else ""
    cur: set[str] = set()
    export_prefix = ""
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^(export\s+)?SLACK_ALLOWED_CHANNELS=(.*)$", s)
        if not m:
            continue
        if m.group(1):
            export_prefix = "export "
        raw = m.group(2).strip().strip('"').strip("'")
        for part in raw.split(","):
            cid = part.strip()
            if cid:
                cur.add(cid)
    merged = (cur - stale_ids) | keep_ids
    new_line = f"{export_prefix}SLACK_ALLOWED_CHANNELS={','.join(sorted(merged))}"
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
    env_path.write_text("\n".join(lines_out) + ("\n" if text.endswith("\n") or not text else ""), encoding="utf-8")
    return env_path


def _prune_role_jobs(home: Path) -> int:
    os.environ["HERMES_HOME"] = str(home)
    from cron.jobs import load_jobs, save_jobs

    jobs = load_jobs()
    kept = [j for j in jobs if not str(j.get("name") or "").startswith("daily-slack-role-status-")]
    removed = len(jobs) - len(kept)
    if removed:
        save_jobs(kept)
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", metavar="PATH", help="Profile directory (default: HERMES_HOME)")
    args = ap.parse_args()

    hh = (args.home or os.environ.get("HERMES_HOME") or "").strip()
    if not hh:
        print("Set HERMES_HOME or pass --home", file=sys.stderr)
        return 2
    home = Path(hh).expanduser()
    if not home.is_dir():
        print(f"Not a directory: {home}", file=sys.stderr)
        return 2

    current = _current_merged_slack_channels(home)
    managed_roles = {slug for _, slug, _ in MANAGED_ROLE_GROUPS}

    tok = _load_slack_env(home)
    by_name = _channels_by_name(tok)

    new_map: dict[str, str] = {}

    # Preserve active existing non-managed mappings (e.g. chief/global channels already curated).
    for cid, slug in current.items():
        slug_s = str(slug).strip()
        if slug_s in managed_roles:
            continue
        info = _slack_api(tok, "conversations.info", channel=str(cid))
        if not info.get("ok"):
            continue
        ch = info.get("channel") or {}
        if ch.get("is_archived"):
            continue
        new_map[str(cid).strip()] = slug_s

    for aliases, slug, ensure_name in MANAGED_ROLE_GROUPS:
        if ensure_name:
            row = _ensure_channel(tok, by_name, ensure_name)
            if row:
                row = _join_if_possible(tok, row)
                by_name[row["name"]] = row
        chosen = None
        for nm in aliases:
            row = by_name.get(nm)
            if row and not row.get("is_archived"):
                chosen = _join_if_possible(tok, row)
                break
        if chosen and chosen.get("id"):
            new_map[str(chosen["id"]).strip()] = slug
        else:
            print(f"skip {slug}: no active channel found for aliases {aliases}", file=sys.stderr)

    overlay = _write_overlay(home, new_map)
    stale_ids = set(str(cid).strip() for cid in current.keys()) - set(new_map.keys())
    env_path = _update_allowlist(home, set(new_map.keys()), stale_ids)
    removed = _prune_role_jobs(home)

    print(f"overlay: {overlay}")
    print(f"allowlist: {env_path}")
    print(f"slack channels: {len(current)} -> {len(new_map)}")
    print(f"removed derived slack role jobs: {removed}")
    for cid, slug in sorted(new_map.items(), key=lambda kv: kv[1]):
        print(f"map {cid} -> {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
