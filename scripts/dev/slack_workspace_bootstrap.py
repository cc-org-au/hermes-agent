#!/usr/bin/env python3
"""
Slack Web API helper (bot token only): print SLACK_ALLOWED_TEAMS / SLACK_ALLOWED_CHANNELS,
join public channels, optionally send a test DM.

The live gateway also needs SLACK_APP_TOKEN (xapp-…) for Socket Mode — this script does not
create that; it only uses SLACK_BOT_TOKEN (xoxb-…) for REST calls.

Usage (from repo root, venv active):
  set -a && source ~/.hermes/.env && set +a
  python scripts/dev/slack_workspace_bootstrap.py [--send-test-dm] [--max-channels 80]
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any


def _urlopen(req: urllib.request.Request, *, timeout: float = 60):
    try:
        import certifi  # type: ignore[import-untyped]

        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except ImportError:
        return urllib.request.urlopen(req, timeout=timeout)


def _api(method: str, token: str, **kwargs: Any) -> dict[str, Any]:
    body = {"token": token, **kwargs}
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with _urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Slack workspace bootstrap via bot token")
    ap.add_argument("--send-test-dm", action="store_true", help="POST test message to SLACK_ALLOWED_USERS DM")
    ap.add_argument("--max-channels", type=int, default=80, help="Max channel IDs to list in SLACK_ALLOWED_CHANNELS")
    args = ap.parse_args()

    tok = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
    if not tok.startswith("xoxb-"):
        print("Error: SLACK_BOT_TOKEN (xoxb-) required in environment.", file=sys.stderr)
        return 1

    auth = _api("auth.test", tok)
    if not auth.get("ok"):
        print(f"auth.test failed: {auth.get('error')}", file=sys.stderr)
        return 1

    team_id = auth.get("team_id") or ""
    team_name = auth.get("team") or ""
    bot_user = auth.get("user_id") or ""
    print(f"# Workspace: {team_name!r} team_id={team_id} bot_user={bot_user}")
    print(f"SLACK_ALLOWED_TEAMS={team_id}")

    cursor = ""
    channel_ids: list[str] = []
    while len(channel_ids) < args.max_channels:
        page = _api(
            "conversations.list",
            tok,
            types="public_channel,private_channel",
            limit=200,
            cursor=cursor or None,
        )
        if not page.get("ok"):
            print(f"conversations.list failed: {page.get('error')}", file=sys.stderr)
            break
        for ch in page.get("channels") or []:
            cid = ch.get("id")
            if isinstance(cid, str) and cid.startswith("C"):
                channel_ids.append(cid)
        cursor = (page.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break

    joined = 0
    for cid in channel_ids[: args.max_channels]:
        j = _api("conversations.join", tok, channel=cid)
        if j.get("ok"):
            joined += 1
        elif j.get("error") not in ("already_in_channel", "method_not_supported_for_channel_type"):
            pass  # missing scope or archived — ignore

    print(f"# Joined {joined} channel(s) (best-effort; needs channels:join scope).")
    if channel_ids:
        csv = ",".join(channel_ids[: args.max_channels])
        print(f"SLACK_ALLOWED_CHANNELS={csv}")
    else:
        print("# No channel IDs collected (check bot scopes: channels:read, groups:read).")

    if args.send_test_dm:
        allow = (os.getenv("SLACK_ALLOWED_USERS") or "").strip()
        if not allow or allow == "*":
            print("Error: set SLACK_ALLOWED_USERS to a member ID (U…) for --send-test-dm", file=sys.stderr)
            return 1
        uid = allow.split(",")[0].strip()
        op = _api("conversations.open", tok, users=uid)
        if not op.get("ok"):
            print(f"conversations.open failed: {op.get('error')}", file=sys.stderr)
            return 1
        ch = (op.get("channel") or {}) if isinstance(op.get("channel"), dict) else {}
        dm = ch.get("id")
        if not dm:
            print("conversations.open: no channel id", file=sys.stderr)
            return 1
        msg = _api(
            "chat.postMessage",
            tok,
            channel=dm,
            text="[Hermes] Slack bootstrap test message — gateway still needs SLACK_APP_TOKEN for Socket Mode.",
        )
        if not msg.get("ok"):
            print(f"chat.postMessage failed: {msg.get('error')}", file=sys.stderr)
            return 1
        print(f"# Test DM sent to channel {dm}")

    if not (os.getenv("SLACK_APP_TOKEN") or "").strip():
        print(
            "# Reminder: set SLACK_APP_TOKEN (xapp-…) for Socket Mode or the gateway Slack adapter stays disconnected.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
