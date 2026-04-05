"""
Slack maintenance helpers (CLI). Uses the Slack Web API with SLACK_BOT_TOKEN —
separate from the gateway Socket Mode adapter.

App configuration tokens (SLACK_CONFIG_TOKEN, xoxe...) are only for Slack's
manifest/tooling APIs (validate/export/update). They do not replace xoxb/xapp
for the live gateway.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from hermes_constants import display_hermes_home


def _slack_manifest_slash_command_features() -> List[Dict[str, Any]]:
    """Build ``features.slash_commands`` for the Slack app manifest (Socket Mode).

    Registers ``/hermes`` plus ``/hermes-<subcommand>`` for each gateway key so
    commands appear in Slack's slash picker; the gateway maps them to the same
    handler as ``/hermes <subcommand>``.
    """
    from hermes_cli.commands import resolve_command, slack_bolt_slash_command_paths

    entries: List[Dict[str, Any]] = [
        {
            "command": "/hermes",
            "description": (
                "Hermes AI — subcommand or free text; see /hermes-help and "
                "other /hermes-* shortcuts"
            ),
            "should_escape": False,
        }
    ]
    for path in slack_bolt_slash_command_paths():
        key = path[len("/hermes-") :]
        if key == "compact":
            desc = "Compress conversation context (same as /hermes compress)"
        else:
            cmd = resolve_command(key)
            desc = cmd.description if cmd else f"Hermes gateway: {key}"
        if len(desc) > 300:
            desc = desc[:297] + "..."
        entries.append({"command": path, "description": desc, "should_escape": False})
    return entries


def hermes_slack_manifest_dict() -> Dict[str, Any]:
    """Hermes-recommended Slack app manifest (v2 JSON) for Socket Mode + Bolt.

    Use with ``apps.manifest.validate`` / ``update`` and a configuration token.
    After changing the manifest, reinstall the app to the workspace and refresh
    ``SLACK_BOT_TOKEN`` / ``SLACK_APP_TOKEN`` in Hermes.
    """
    long_description = (
        "Hermes Agent connects Slack to the Hermes AI gateway using Bolt Socket Mode, "
        "so no public HTTP endpoint is required. Install this app to your workspace, "
        "then copy the Bot User OAuth Token (xoxb) and an App-Level Token with "
        "connections:write (xapp) into your Hermes ~/.hermes/.env. Subscribe to the "
        "documented bot events and bot token scopes so channel DMs and @mentions work."
    )
    if len(long_description) < 174:
        long_description = (long_description + " ") * 6

    return {
        "_metadata": {"major_version": 2, "minor_version": 1},
        "display_information": {
            "name": "Hermes Agent",
            "description": "AI agent gateway (Hermes) via Socket Mode",
            "background_color": "#2c2d30",
            "long_description": long_description,
        },
        "features": {
            "app_home": {
                "home_tab_enabled": True,
                "messages_tab_enabled": True,
                "messages_tab_read_only_enabled": False,
            },
            "bot_user": {
                "display_name": "hermes",
                "always_online": True,
            },
            "slash_commands": _slack_manifest_slash_command_features(),
        },
        "oauth_config": {
            "scopes": {
                "bot": [
                    "app_mentions:read",
                    "channels:history",
                    "channels:join",
                    "channels:read",
                    "chat:write",
                    "commands",
                    "files:read",
                    "files:write",
                    "groups:history",
                    "groups:read",
                    "im:history",
                    "im:read",
                    "im:write",
                    "mpim:history",
                    "mpim:read",
                    "reactions:read",
                    "reactions:write",
                    "users:read",
                ]
            }
        },
        "settings": {
            "org_deploy_enabled": False,
            "socket_mode_enabled": True,
            "token_rotation_enabled": False,
            "is_hosted": False,
            "event_subscriptions": {
                "bot_events": [
                    "app_mention",
                    "message.channels",
                    "message.groups",
                    "message.im",
                    "message.mpim",
                ]
            },
            "interactivity": {"is_enabled": True},
        },
    }


def _config_token_from_env() -> str:
    raw = (
        os.getenv("SLACK_CONFIG_TOKEN") or os.getenv("SLACK_APP_CONFIG_TOKEN") or ""
    ).strip()
    if not raw:
        print(
            "Error: SLACK_CONFIG_TOKEN is not set.\n"
            "Generate an app configuration token at https://api.slack.com/apps "
            "(Your App Configuration Tokens → Generate Token). "
            "It starts with xoxe. This is NOT your bot token (xoxb) or app token (xapp).",
            file=sys.stderr,
        )
        sys.exit(1)
    return raw


def _slack_tooling_api(method: str, **fields: Optional[str]) -> Dict[str, Any]:
    """POST to Slack Web API using an app configuration token (form body)."""
    token = _config_token_from_env()
    payload: Dict[str, str] = {"token": token}
    for k, v in fields.items():
        if v is not None:
            payload[k] = v
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            print(f"HTTP {e.code}: {body[:800]}", file=sys.stderr)
            sys.exit(1)


def slack_config_test() -> None:
    """Verify SLACK_CONFIG_TOKEN with auth.test (tooling token, not xoxb/xapp)."""
    j = _slack_tooling_api("auth.test")
    if not j.get("ok"):
        print(f"auth.test failed: {j.get('error')}", file=sys.stderr)
        sys.exit(1)
    print(
        f"ok=true team={j.get('team')} team_id={j.get('team_id')} "
        f"user={j.get('user')} user_id={j.get('user_id')}"
    )
    print(
        "This is an app configuration token — use it only for manifest validate/export/update."
    )
    print(
        "The Hermes gateway still requires SLACK_BOT_TOKEN (xoxb) and "
        "SLACK_APP_TOKEN (xapp) after you install/reinstall the app."
    )


def slack_manifest_validate(*, app_id: Optional[str] = None) -> None:
    """Validate the built-in Hermes manifest via apps.manifest.validate."""
    manifest = hermes_slack_manifest_dict()
    kwargs: Dict[str, Optional[str]] = {
        "manifest": json.dumps(manifest, separators=(",", ":")),
    }
    if app_id:
        kwargs["app_id"] = app_id.strip()
    j = _slack_tooling_api("apps.manifest.validate", **kwargs)
    if not j.get("ok"):
        print(f"validate failed: {j.get('error')}", file=sys.stderr)
        for err in j.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print("ok=true Hermes Slack manifest validates against Slack's schema.")
    if app_id:
        print("(Validated in context of existing app_id — safe to consider manifest.update.)")


def slack_manifest_export(*, app_id: str) -> None:
    """Export the current Slack app manifest (JSON) for inspection."""
    aid = app_id.strip()
    if not aid:
        print("Error: --app-id is required", file=sys.stderr)
        sys.exit(1)
    j = _slack_tooling_api("apps.manifest.export", app_id=aid)
    if not j.get("ok"):
        print(f"export failed: {j.get('error')}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(j.get("manifest"), indent=2, sort_keys=True))


def slack_manifest_update(*, app_id: str) -> None:
    """Replace the Slack app configuration with the built-in Hermes manifest."""
    aid = app_id.strip()
    if not aid:
        print("Error: --app-id is required", file=sys.stderr)
        sys.exit(1)
    manifest = hermes_slack_manifest_dict()
    j = _slack_tooling_api(
        "apps.manifest.update",
        app_id=aid,
        manifest=json.dumps(manifest, separators=(",", ":")),
    )
    if not j.get("ok"):
        print(f"update failed: {j.get('error')}", file=sys.stderr)
        for err in j.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print(f"ok=true app_id={j.get('app_id')} permissions_updated={j.get('permissions_updated')}")
    print("Reinstall the app to the workspace, then update SLACK_BOT_TOKEN and SLACK_APP_TOKEN in Hermes.")


def _tokens_from_env() -> List[str]:
    raw = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
    if not raw:
        print(
            "Error: SLACK_BOT_TOKEN is not set.\n"
            f"Add it to {display_hermes_home()}/.env (or export it), then retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    return [t.strip() for t in raw.split(",") if t.strip()]


def slack_resolve_user(*, email: Optional[str] = None, search: Optional[str] = None) -> None:
    """Resolve a human member id (U…) via Slack Web API for allowlists."""
    if (email and search) or (not email and not search):
        print("Error: specify exactly one of --email or --search", file=sys.stderr)
        sys.exit(1)

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print(
            "Error: slack_sdk is not installed. Run: pip install 'hermes-agent[slack]'",
            file=sys.stderr,
        )
        sys.exit(1)

    token = _tokens_from_env()[0]
    client = WebClient(token=token)

    if email:
        em = email.strip()
        try:
            resp = client.users_lookupByEmail(email=em)
        except SlackApiError as e:
            err = e.response.get("error", "")
            if err == "missing_scope":
                print(
                    "users.lookupByEmail failed: missing **users:read.email** bot scope.\n"
                    "Add it under OAuth & Permissions → Bot Token Scopes, reinstall the app, "
                    "or use: hermes slack resolve-user --search \"your name\"",
                    file=sys.stderr,
                )
            elif err == "users_not_found":
                print(f"No user found for email {em!r}", file=sys.stderr)
            else:
                print(f"users.lookupByEmail failed: {err}", file=sys.stderr)
            sys.exit(1)
        u = resp.get("user") or {}
        prof = u.get("profile") or {}
        print(
            f"member_id={u.get('id', '?')}\t"
            f"name={u.get('name', '')}\t"
            f"display_name={prof.get('display_name', '')}\t"
            f"real_name={prof.get('real_name', '')}\t"
            f"email={prof.get('email', '')}"
        )
        return

    q = (search or "").strip().lower()
    if len(q) < 2:
        print("Error: --search must be at least 2 characters", file=sys.stderr)
        sys.exit(1)

    matches: List[dict] = []
    cursor = None
    try:
        while True:
            resp = client.users_list(limit=200, cursor=cursor)
            for m in resp.get("members") or []:
                if m.get("is_bot") or m.get("deleted"):
                    continue
                prof = m.get("profile") or {}
                hay = " ".join(
                    [
                        str(m.get("name") or ""),
                        str(prof.get("display_name") or ""),
                        str(prof.get("real_name") or ""),
                        str(prof.get("email") or ""),
                    ]
                ).lower()
                if q in hay:
                    matches.append(m)
            cursor = (resp.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
    except SlackApiError as e:
        err = e.response.get("error", "")
        if err == "missing_scope":
            print(
                "users.list failed: missing **users:read** bot scope.\n"
                "Add it under OAuth & Permissions → Bot Token Scopes, then reinstall the app.",
                file=sys.stderr,
            )
        else:
            print(f"users.list failed: {err}", file=sys.stderr)
        sys.exit(1)

    if not matches:
        print(f"No members matched --search {search!r}", file=sys.stderr)
        sys.exit(1)

    max_show = 30
    for m in matches[:max_show]:
        prof = m.get("profile") or {}
        print(
            f"member_id={m.get('id', '?')}\t"
            f"name={m.get('name', '')}\t"
            f"display_name={prof.get('display_name', '')}\t"
            f"real_name={prof.get('real_name', '')}\t"
            f"email={prof.get('email', '')}"
        )
    if len(matches) > max_show:
        print(f"(… {len(matches) - max_show} more matches not shown; narrow --search)", file=sys.stderr)


def slack_whoami() -> None:
    """Print bot identity from auth.test (no tokens printed)."""
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print(
            "Error: slack_sdk is not installed. Run: pip install 'hermes-agent[slack]'",
            file=sys.stderr,
        )
        sys.exit(1)

    tokens = _tokens_from_env()
    for i, token in enumerate(tokens):
        prefix = f"[token {i + 1}] " if len(tokens) > 1 else ""
        try:
            client = WebClient(token=token)
            data = client.auth_test()
            print(
                f"{prefix}team={data.get('team', '?')} "
                f"bot_user_id={data.get('user_id', '?')} "
                f"bot_username=@{data.get('user', '?')}"
            )
        except SlackApiError as e:
            print(f"{prefix}auth.test failed: {e.response.get('error', e)}", file=sys.stderr)
            sys.exit(1)


def slack_join_public_channels(*, dry_run: bool = False) -> None:
    """Join every public channel the bot is not already in (needs channels:join)."""
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print(
            "Error: slack_sdk is not installed. Run: pip install 'hermes-agent[slack]'",
            file=sys.stderr,
        )
        sys.exit(1)

    joined = 0
    skipped = 0
    errors = 0
    would_join = 0
    tokens = _tokens_from_env()

    for ti, token in enumerate(tokens):
        label = f"[workspace {ti + 1}] " if len(tokens) > 1 else ""
        client = WebClient(token=token)
        try:
            ident = client.auth_test()
        except SlackApiError as e:
            print(f"{label}auth.test failed: {e.response.get('error', e)}", file=sys.stderr)
            sys.exit(1)
        team = ident.get("team", "?")
        print(f"{label}Joining public channels in team {team!r} …")

        cursor = None
        channels: List[dict] = []
        while True:
            try:
                resp = client.conversations_list(
                    types="public_channel",
                    exclude_archived=True,
                    limit=200,
                    cursor=cursor,
                )
            except SlackApiError as e:
                err = e.response.get("error", "")
                if err == "missing_scope":
                    print(
                        f"{label}Error: missing OAuth scope. Add **channels:join** under "
                        "OAuth & Permissions → Bot Token Scopes, then reinstall the app to the workspace.",
                        file=sys.stderr,
                    )
                else:
                    print(f"{label}conversations.list failed: {err}", file=sys.stderr)
                sys.exit(1)
            channels.extend(resp.get("channels") or [])
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        for ch in channels:
            cid = ch.get("id")
            name = ch.get("name", cid)
            if not cid:
                continue
            if ch.get("is_member"):
                skipped += 1
                continue
            if dry_run:
                print(f"  would join #{name} ({cid})")
                would_join += 1
                continue
            try:
                client.conversations_join(channel=cid)
                print(f"  joined #{name}")
                joined += 1
                time.sleep(0.35)  # light rate-limit courtesy
            except SlackApiError as e:
                err = e.response.get("error", "")
                if err in ("already_in_channel", "channel_not_found"):
                    skipped += 1
                    continue
                print(f"  #{name}: {err}", file=sys.stderr)
                errors += 1

    if dry_run:
        print(f"Done (dry run). would_join={would_join} already_member={skipped} errors={errors}")
    else:
        print(f"Done. joined={joined} already_member_or_skipped={skipped} errors={errors}")
    if errors and not dry_run:
        sys.exit(1)


def slack_command(args) -> None:
    """Dispatch `hermes slack …` subcommands."""
    sub = getattr(args, "slack_command", None) or ""
    if sub == "join-public":
        slack_join_public_channels(dry_run=bool(getattr(args, "dry_run", False)))
    elif sub == "resolve-user":
        slack_resolve_user(
            email=getattr(args, "resolve_user_email", None) or None,
            search=getattr(args, "resolve_user_search", None) or None,
        )
    elif sub == "whoami":
        slack_whoami()
    elif sub == "config-test":
        slack_config_test()
    elif sub == "manifest-validate":
        slack_manifest_validate(app_id=getattr(args, "app_id", None) or None)
    elif sub == "manifest-export":
        slack_manifest_export(app_id=getattr(args, "app_id", "") or "")
    elif sub == "manifest-update":
        if not getattr(args, "confirm", False):
            print(
                "Refusing to rewrite your Slack app without --confirm.\n"
                "This replaces the app configuration; reinstall the app afterward.",
                file=sys.stderr,
            )
            sys.exit(1)
        slack_manifest_update(app_id=getattr(args, "app_id", "") or "")
    else:
        print(f"Unknown slack subcommand: {sub!r}", file=sys.stderr)
        sys.exit(1)
