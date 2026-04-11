"""
Slack maintenance helpers (CLI). Uses the Slack Web API with SLACK_BOT_TOKEN —
separate from the gateway Socket Mode adapter.

App configuration tokens (SLACK_CONFIG_TOKEN, xoxe...) are only for Slack's
manifest/tooling APIs (validate/export/update). They do not replace xoxb/xapp
for the live gateway.
"""

from __future__ import annotations

import copy
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import display_hermes_home

# OAuth needs at least one redirect URL. Hermes is Socket Mode–only (no OAuth callback server);
# this URL satisfies Slack’s authorize URL. Prefer **Install to Workspace** on api.slack.com/apps
# OAuth & Permissions, or append matching **redirect_uri** to the authorize link.
_DEFAULT_SLACK_OAUTH_REDIRECT_URLS: List[str] = ["https://localhost/slack/oauth_redirect"]


def _slack_urlopen(req: urllib.request.Request, *, timeout: float = 90):
    """HTTPS to Slack with certifi CA bundle when available (avoids macOS Python SSL errors)."""
    try:
        import certifi  # type: ignore[import-untyped]

        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except ImportError:
        return urllib.request.urlopen(req, timeout=timeout)


def _config_token_operator_preferred() -> str:
    """Prefer ``SLACK_CONFIG_TOKEN_OPERATOR`` for ``apps.manifest.create`` (qow / operator account)."""
    from hermes_cli.config import get_env_value

    for key in (
        "SLACK_CONFIG_TOKEN_OPERATOR",
        "SLACK_CONFIG_TOKEN",
        "SLACK_APP_CONFIG_TOKEN",
        "SLACK_MANIFEST_KEY",
    ):
        v = (get_env_value(key) or "").strip()
        if v:
            return v
    print(
        "Error: set SLACK_CONFIG_TOKEN_OPERATOR (recommended for this command) or "
        "SLACK_CONFIG_TOKEN / SLACK_MANIFEST_KEY (xoxe app configuration token).",
        file=sys.stderr,
    )
    sys.exit(1)


def normalize_slack_manifest_v2_for_api(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure v2 manifest fields Slack expects: metadata, long_description length, redirect URLs."""
    m = copy.deepcopy(manifest)
    m.setdefault("_metadata", {"major_version": 2, "minor_version": 1})
    disp = m.setdefault("display_information", {})
    if not isinstance(disp, dict):
        disp = {}
        m["display_information"] = disp
    ld = disp.get("long_description") or ""
    long_description = str(ld)
    if len(long_description) < 174:
        long_description = (long_description + " ") * 6
    while len(long_description) < 174:
        long_description = long_description + " "
    disp["long_description"] = long_description[:4000]
    _merge_oauth_redirect_urls(m, _DEFAULT_SLACK_OAUTH_REDIRECT_URLS)
    st = m.setdefault("settings", {})
    if isinstance(st, dict):
        st.setdefault("is_hosted", False)
    return m


def slack_manifest_create_from_json_file(*, path: str) -> None:
    """Load a JSON manifest file, normalize, validate, and ``apps.manifest.create``."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        print(f"Error: manifest file not found: {p}", file=sys.stderr)
        sys.exit(1)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"Error reading manifest JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(raw, dict):
        print("Error: manifest JSON must be an object at the top level.", file=sys.stderr)
        sys.exit(1)

    tok = _config_token_operator_preferred()
    from hermes_cli.config import get_env_value

    if (get_env_value("SLACK_CONFIG_TOKEN_OPERATOR") or "").strip():
        print(
            "manifest-create-from-json: using SLACK_CONFIG_TOKEN_OPERATOR (new app owned by that account).",
            file=sys.stderr,
        )

    m = normalize_slack_manifest_v2_for_api(raw)
    manifest_json = json.dumps(m, separators=(",", ":"))

    val = _slack_tooling_api_with_token("apps.manifest.validate", tok, manifest=manifest_json)
    if not val.get("ok"):
        print(f"validate failed: {val.get('error')}", file=sys.stderr)
        for err in val.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    created = _slack_tooling_api_with_token("apps.manifest.create", tok, manifest=manifest_json)
    if not created.get("ok"):
        print(f"create failed: {created.get('error')}", file=sys.stderr)
        for err in created.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    new_id = created.get("app_id", "")
    creds = created.get("credentials") or {}
    oauth_url = created.get("oauth_authorize_url", "")
    print("ok=true")
    print(f"new_app_id={new_id}")
    if oauth_url:
        print(f"oauth_authorize_url={oauth_url}")
    print(
        "\nSave the credentials below once — treat like passwords. "
        "Install the app to your workspace, then add SLACK_BOT_TOKEN (xoxb) and "
        "SLACK_APP_TOKEN (xapp) to Hermes .env.\n",
        file=sys.stderr,
    )
    print(json.dumps({"credentials": creds}, indent=2))


def _merge_oauth_redirect_urls(manifest: Dict[str, Any], urls: List[str]) -> None:
    """Ensure oauth_config.redirect_urls includes each URL (order-preserving, no duplicates)."""
    oc = manifest.get("oauth_config")
    if not isinstance(oc, dict):
        oc = {}
        manifest["oauth_config"] = oc
    existing = oc.get("redirect_urls")
    if not isinstance(existing, list):
        existing = []
    seen = {str(u).strip() for u in existing if str(u).strip()}
    for u in urls:
        u = u.strip()
        if u and u not in seen:
            existing.append(u)
            seen.add(u)
    oc["redirect_urls"] = existing


def _config_token_raw() -> str:
    """Resolve Slack app configuration token (xoxe) from env or Hermes ``~/.hermes/.env``."""
    from hermes_cli.config import get_env_value

    for key in ("SLACK_CONFIG_TOKEN", "SLACK_APP_CONFIG_TOKEN", "SLACK_MANIFEST_KEY"):
        v = (get_env_value(key) or "").strip()
        if v:
            return v
    return ""


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
            "redirect_urls": list(_DEFAULT_SLACK_OAUTH_REDIRECT_URLS),
            "scopes": {
                "bot": [
                    "app_mentions:read",
                    "channels:history",
                    "channels:join",
                    "channels:manage",
                    "channels:read",
                    "chat:write",
                    "commands",
                    "files:read",
                    "files:write",
                    "groups:history",
                    "groups:read",
                    "groups:write",
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
    raw = _config_token_raw()
    if not raw:
        print(
            "Error: SLACK_CONFIG_TOKEN is not set (or empty after loading env files).\n"
            "Alias: SLACK_MANIFEST_KEY (same value — Slack app configuration token xoxe…).\n"
            "For `manifest-clone` under two Slack developer accounts, set both "
            "SLACK_CONFIG_TOKEN_DROPLET (export source app) and SLACK_CONFIG_TOKEN_OPERATOR "
            "(validate/create the new app).\n"
            f"Values are read from the environment and from {display_hermes_home()}/.env (HERMES_HOME).\n"
            "Generate an app configuration token at https://api.slack.com/apps "
            "(Your App → App configuration tokens → Generate token). "
            "It is NOT your bot token (xoxb) or Socket Mode app token (xapp).\n"
            "\n"
            "Shell: you must export the variable so the Python process inherits it:\n"
            "  export SLACK_CONFIG_TOKEN='xoxe-…'\n"
            "A line like `SLACK_CONFIG_TOKEN=…` alone (without export) does not pass the value to `hermes`.\n"
            "\n"
            "If you did export but still see this: ~/.hermes/.env (and profile .env) load with "
            "override — a line `SLACK_CONFIG_TOKEN=` with no value clears your export. "
            "Remove that line or put the full token in the file.",
            file=sys.stderr,
        )
        sys.exit(1)
    return raw


def _manifest_clone_tokens() -> tuple[str, str, bool]:
    """Return (token_for_export, token_for_validate_and_create, split_mode).

    When **both** ``SLACK_CONFIG_TOKEN_DROPLET`` and ``SLACK_CONFIG_TOKEN_OPERATOR`` are set,
    export uses the droplet account (must manage the source app); validate/create use the
    operator account (owns the new app). Otherwise a single ``SLACK_CONFIG_TOKEN`` / alias is used.
    """
    from hermes_cli.config import get_env_value

    droplet = (get_env_value("SLACK_CONFIG_TOKEN_DROPLET") or "").strip()
    operator = (get_env_value("SLACK_CONFIG_TOKEN_OPERATOR") or "").strip()
    if droplet and operator:
        return droplet, operator, True
    if droplet or operator:
        print(
            "Error: for `hermes slack manifest-clone`, set **both** "
            "SLACK_CONFIG_TOKEN_DROPLET and SLACK_CONFIG_TOKEN_OPERATOR "
            "(export vs create under different Slack developer logins), "
            "or set neither and use SLACK_CONFIG_TOKEN / SLACK_MANIFEST_KEY only.",
            file=sys.stderr,
        )
        sys.exit(1)
    single = _config_token_raw()
    if not single:
        print(
            "Error: no Slack app configuration token found for manifest-clone.\n"
            "Set SLACK_CONFIG_TOKEN (or SLACK_MANIFEST_KEY), or set both "
            "SLACK_CONFIG_TOKEN_DROPLET and SLACK_CONFIG_TOKEN_OPERATOR.",
            file=sys.stderr,
        )
        sys.exit(1)
    return single, single, False


def _slack_tooling_api_with_token(method: str, token: str, **fields: Optional[str]) -> Dict[str, Any]:
    """POST to Slack Web API using the given app configuration token (form body)."""
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
        with _slack_urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(
            f"Slack API request failed: {e.reason}\n"
            "If you see SSL certificate errors on macOS, install certificates for your Python "
            "or ensure the `certifi` package is installed (Hermes uses certifi for HTTPS when available).",
            file=sys.stderr,
        )
        sys.exit(1)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            print(f"HTTP {e.code}: {body[:800]}", file=sys.stderr)
            sys.exit(1)


def _slack_tooling_api(method: str, **fields: Optional[str]) -> Dict[str, Any]:
    """POST to Slack Web API using ``SLACK_CONFIG_TOKEN`` (or aliases) from env."""
    return _slack_tooling_api_with_token(method, _config_token_from_env(), **fields)


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
    _cmds = _slack_manifest_slash_command_features()
    print("ok=true Hermes Slack manifest validates against Slack's schema.")
    print(f"Slash commands in manifest: {len(_cmds)} ( /hermes plus /hermes-* shortcuts ).")
    print("After Hermes upgrades: hermes slack manifest-update --confirm --app-id <A0…>")
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


def _manifest_from_export_response(j: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize apps.manifest.export ``manifest`` field to a dict."""
    m = j.get("manifest")
    if m is None:
        return {}
    if isinstance(m, dict):
        return m
    if isinstance(m, str):
        return json.loads(m)
    raise TypeError(f"unexpected manifest type: {type(m)}")


def _default_bot_display_name(display_name: str) -> str:
    """Slack bot display name: short, no spaces (Hermes uses ``hermes``)."""
    s = display_name.strip().lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9._-]", "", s)
    if not s:
        s = "hermes-bot"
    return s[:80]


def slack_manifest_clone_from_app(
    *,
    source_app_id: str,
    new_display_name: str,
    bot_display_name: Optional[str] = None,
) -> None:
    """Export an existing app's manifest, rename it, create a new Slack app (apps.manifest.create)."""
    src = source_app_id.strip()
    if not src:
        print("Error: --source-app-id is required", file=sys.stderr)
        sys.exit(1)
    name = new_display_name.strip()
    if not name:
        print("Error: --new-name must be non-empty", file=sys.stderr)
        sys.exit(1)

    ex_tok, cr_tok, split_clone = _manifest_clone_tokens()
    if split_clone:
        print(
            "manifest-clone: using SLACK_CONFIG_TOKEN_DROPLET for export, "
            "SLACK_CONFIG_TOKEN_OPERATOR for validate/create (new app owned by operator account).",
            file=sys.stderr,
        )

    ex = _slack_tooling_api_with_token("apps.manifest.export", ex_tok, app_id=src)
    if not ex.get("ok"):
        print(f"export failed: {ex.get('error')}", file=sys.stderr)
        sys.exit(1)
    manifest = copy.deepcopy(_manifest_from_export_response(ex))

    disp = manifest.get("display_information")
    if not isinstance(disp, dict):
        disp = {}
        manifest["display_information"] = disp
    disp["name"] = name

    bot_dn = (bot_display_name or "").strip() or _default_bot_display_name(name)
    feats = manifest.get("features")
    if isinstance(feats, dict):
        bu = feats.get("bot_user")
        if not isinstance(bu, dict):
            bu = {}
            feats["bot_user"] = bu
        bu["display_name"] = bot_dn

    _merge_oauth_redirect_urls(manifest, _DEFAULT_SLACK_OAUTH_REDIRECT_URLS)

    manifest_json = json.dumps(manifest, separators=(",", ":"))

    val = _slack_tooling_api_with_token(
        "apps.manifest.validate",
        cr_tok,
        manifest=manifest_json,
    )
    if not val.get("ok"):
        print(f"validate failed: {val.get('error')}", file=sys.stderr)
        for err in val.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    created = _slack_tooling_api_with_token("apps.manifest.create", cr_tok, manifest=manifest_json)
    if not created.get("ok"):
        print(f"create failed: {created.get('error')}", file=sys.stderr)
        for err in created.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    new_id = created.get("app_id", "")
    creds = created.get("credentials") or {}
    oauth_url = created.get("oauth_authorize_url", "")
    print("ok=true")
    print(f"new_app_id={new_id}")
    print(f"source_app_id={src}")
    print(f"display_name={name!r}")
    print(f"bot_display_name={bot_dn!r}")
    if oauth_url:
        print(f"oauth_authorize_url={oauth_url}")
    print(
        "\nSave the credentials below once — treat like passwords. "
        "Install the app to your workspace from the OAuth URL, then add "
        "SLACK_BOT_TOKEN (xoxb) and SLACK_APP_TOKEN (xapp) to Hermes .env.\n",
        file=sys.stderr,
    )
    print(json.dumps({"credentials": creds}, indent=2))


def slack_manifest_patch_oauth_install(
    *,
    app_id: str,
    bot_display_name: Optional[str] = None,
    extra_redirect_urls: Optional[List[str]] = None,
) -> None:
    """Export an app manifest, add OAuth redirect URL(s), optionally rename bot user; apps.manifest.update."""
    aid = app_id.strip()
    if not aid:
        print("Error: --app-id is required", file=sys.stderr)
        sys.exit(1)

    ex = _slack_tooling_api("apps.manifest.export", app_id=aid)
    if not ex.get("ok"):
        print(f"export failed: {ex.get('error')}", file=sys.stderr)
        sys.exit(1)
    manifest = copy.deepcopy(_manifest_from_export_response(ex))

    urls = list(_DEFAULT_SLACK_OAUTH_REDIRECT_URLS)
    if extra_redirect_urls:
        urls.extend(u.strip() for u in extra_redirect_urls if u and str(u).strip())
    _merge_oauth_redirect_urls(manifest, urls)

    bdn = (bot_display_name or "").strip()
    if bdn:
        feats = manifest.get("features")
        if not isinstance(feats, dict):
            feats = {}
            manifest["features"] = feats
        bu = feats.get("bot_user")
        if not isinstance(bu, dict):
            bu = {}
            feats["bot_user"] = bu
        bu["display_name"] = bdn

    manifest_json = json.dumps(manifest, separators=(",", ":"))
    val = _slack_tooling_api(
        "apps.manifest.validate",
        app_id=aid,
        manifest=manifest_json,
    )
    if not val.get("ok"):
        print(f"validate failed: {val.get('error')}", file=sys.stderr)
        for err in val.get("errors") or []:
            if isinstance(err, dict):
                print(f"  - {err.get('pointer')}: {err.get('message')}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    j = _slack_tooling_api(
        "apps.manifest.update",
        app_id=aid,
        manifest=manifest_json,
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
    print(
        "OAuth: add **redirect_uri** to your install link so it matches a configured URL, e.g.\n"
        "  redirect_uri=https%3A%2F%2Flocalhost%2Fslack%2Foauth_redirect\n"
        "Or use **Install to Workspace** on the app’s OAuth & Permissions page (no custom link)."
    )
    print("Reinstall the app if Slack prompts, then refresh SLACK_BOT_TOKEN / SLACK_APP_TOKEN in Hermes.")


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


def slack_list_local_commands() -> None:
    """Print slash command names Hermes puts in the Socket Mode manifest (no Slack API call)."""
    from hermes_cli.commands import slack_bolt_slash_command_paths

    primary = ["/hermes"]
    rest = sorted(slack_bolt_slash_command_paths())
    all_cmds = primary + rest
    print(f"Hermes registry → Slack manifest: {len(all_cmds)} slash commands\n")
    for i, c in enumerate(all_cmds, 1):
        print(f"  {i:4d}  {c}")
    print(
        "\nCompare with Slack: api.slack.com/apps → your app → Slash Commands, "
        "or:  hermes slack manifest-export --app-id A0…  (needs SLACK_CONFIG_TOKEN)"
    )
    print(
        "Align with:  export SLACK_CONFIG_TOKEN='xoxe-…'  "
        "&& hermes slack manifest-update --confirm --app-id A0…"
    )


def slack_operator_guide() -> None:
    """Print how Slack slash commands and @profile interact with Hermes."""
    from hermes_cli.commands import slack_bolt_slash_command_paths

    n_short = len(slack_bolt_slash_command_paths())
    print("Hermes + Slack — slash commands and @profile\n")
    print(
        "SECURITY: Never paste SLACK_CONFIG_TOKEN (xoxe), xoxb, or xapp in chat or tickets — "
        "revoke and rotate if exposed.\n"
    )
    print("SLASH COMMANDS\n")
    print(
        "Slack only delivers slash invocations that exist on your Slack app. "
        "Hermes registers a Bolt listener for /hermes and every /hermes-<subcommand> "
        f"({n_short} registry shortcuts), but Slack's app manifest must list each command too."
    )
    print("\nIf /hermes-help (etc.) does nothing or never appears in the composer:\n")
    print("  1. Create SLACK_CONFIG_TOKEN (xoxe) at api.slack.com/apps → App configuration tokens")
    print("     (Hermes also accepts SLACK_MANIFEST_KEY=… for the same token.)")
    print("  2. export SLACK_CONFIG_TOKEN='xoxe-…'")
    print("  3. hermes slack manifest-validate --app-id YOUR_APP_ID")
    print("  4. hermes slack manifest-update --confirm --app-id YOUR_APP_ID")
    print(
        "  Or duplicate an app:  hermes slack manifest-clone --source-app-id A0… "
        "--new-name hermes-operator"
    )
    print(
        "  5. In the Slack app site: reinstall the app to the workspace "
        "(OAuth & Permissions — this refreshes scopes and slash commands)."
    )
    print("  6. Copy the new Bot User OAuth Token (xoxb) and App-Level Token (xapp) into")
    print(f"     {display_hermes_home()}/.env — then restart the gateway.\n")
    print("WORKAROUND (only needs one slash command in Slack):\n")
    print("  Type:  /hermes <subcommand> <args>")
    print("  Example:  /hermes help     /hermes compact")
    print("  (Same behavior as /hermes-help when the shortcut is registered.)\n")
    print("@PROFILE (one-turn Hermes profile override)\n")
    print("  • Profiles are directories: ~/.hermes/profiles/<slug>/")
    print("    Create:  hermes profile create <slug>")
    print("  • In a channel: @mention the bot, then @<slug>, then your message, e.g.:")
    print("      @YourBot @security-director Audit this Dockerfile")
    print("  • In a DM with the bot: start with @<slug> then the message (no bot @ needed).")
    print("  • Slug: lowercase letters, digits, hyphens, underscores; not @file: / @folder: / @diff.\n")


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
    elif sub == "manifest-clone":
        slack_manifest_clone_from_app(
            source_app_id=getattr(args, "source_app_id", "") or "",
            new_display_name=getattr(args, "new_name", "") or "",
            bot_display_name=getattr(args, "bot_display_name", None) or None,
        )
    elif sub == "manifest-create-from-json":
        if not getattr(args, "confirm", False):
            print(
                "Refusing to create a Slack app without --confirm.\n"
                "This calls apps.manifest.create with your JSON file.",
                file=sys.stderr,
            )
            sys.exit(1)
        slack_manifest_create_from_json_file(path=getattr(args, "manifest_file", "") or "")
    elif sub == "manifest-patch-oauth":
        if not getattr(args, "confirm", False):
            print(
                "Refusing to patch the Slack app manifest without --confirm.\n"
                "This updates OAuth redirect URLs (and optional bot display name) via apps.manifest.update.",
                file=sys.stderr,
            )
            sys.exit(1)
        extra_ru = getattr(args, "redirect_url", None) or []
        slack_manifest_patch_oauth_install(
            app_id=getattr(args, "app_id", "") or "",
            bot_display_name=getattr(args, "bot_display_name", None) or None,
            extra_redirect_urls=list(extra_ru) if extra_ru else None,
        )
    elif sub == "manifest-update":
        if not getattr(args, "confirm", False):
            print(
                "Refusing to rewrite your Slack app without --confirm.\n"
                "This replaces the app configuration; reinstall the app afterward.",
                file=sys.stderr,
            )
            sys.exit(1)
        slack_manifest_update(app_id=getattr(args, "app_id", "") or "")
    elif sub == "operator-guide":
        slack_operator_guide()
    elif sub == "list-commands":
        slack_list_local_commands()
    else:
        print(f"Unknown slack subcommand: {sub!r}", file=sys.stderr)
        sys.exit(1)
