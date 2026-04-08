"""Slack channel and Telegram forum-topic admin via platform APIs.

Uses ``SLACK_BOT_TOKEN`` and ``TELEGRAM_BOT_TOKEN`` from the active Hermes env
(same tokens as the gateway). Does not require a running gateway process.

Telegram forum APIs apply to **forum-enabled** supergroups; private chats and
non-forum groups return API errors — pass the numeric ``chat_id`` of a forum group.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SLACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def _ensure_dotenv() -> None:
    try:
        from hermes_cli.env_loader import load_hermes_dotenv
        from hermes_constants import get_hermes_home

        load_hermes_dotenv(hermes_home=get_hermes_home())
    except Exception:
        pass


def _check_slack_token() -> bool:
    _ensure_dotenv()
    import os

    return bool(os.getenv("SLACK_BOT_TOKEN", "").strip())


def _check_telegram_token() -> bool:
    _ensure_dotenv()
    import os

    return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())


def _normalize_slack_channel_name(name: str) -> str:
    s = (name or "").strip().lstrip("#").lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9_-]", "", s)
    return s


def _slack_channel_admin_handler(args: dict, **kw) -> str:
    action = (args.get("action") or "").strip().lower()
    if action not in ("create", "rename", "archive"):
        return json.dumps({"error": "action must be 'create', 'rename', or 'archive'"})

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        return json.dumps(
            {"error": "slack_sdk is not installed. Run: pip install 'hermes-agent[slack]'"}
        )

    _ensure_dotenv()
    import os

    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        return json.dumps({"error": "SLACK_BOT_TOKEN is not set"})

    client = WebClient(token=token)

    try:
        if action == "create":
            raw_name = args.get("name") or ""
            name = _normalize_slack_channel_name(raw_name)
            if not name or not _SLACK_NAME_RE.match(name):
                return json.dumps(
                    {
                        "error": (
                            "Invalid channel name after normalization. Use 1–80 chars: "
                            "lowercase letters, digits, hyphens; must start/end with "
                            "alphanumeric. Given (normalized): "
                            + repr(name)
                        )
                    }
                )
            is_private = bool(args.get("is_private", False))
            team_id = (args.get("team_id") or "").strip() or None
            api_kwargs: Dict[str, Any] = {"name": name, "is_private": is_private}
            if team_id:
                api_kwargs["team_id"] = team_id
            resp = client.conversations_create(**api_kwargs)
            return json.dumps(resp.data if hasattr(resp, "data") else dict(resp))

        channel_id = (args.get("channel_id") or "").strip()
        if not channel_id:
            return json.dumps({"error": "channel_id is required for rename and archive"})
        team_id = (args.get("team_id") or "").strip() or None

        if action == "rename":
            new_name = _normalize_slack_channel_name(args.get("new_name") or "")
            if not new_name or not _SLACK_NAME_RE.match(new_name):
                return json.dumps({"error": "new_name is invalid or missing after normalization"})
            resp = client.conversations_rename(channel=channel_id, name=new_name)
            return json.dumps(resp.data if hasattr(resp, "data") else dict(resp))

        # archive
        resp = client.conversations_archive(channel=channel_id)
        return json.dumps(resp.data if hasattr(resp, "data") else dict(resp))

    except SlackApiError as e:
        err = e.response.get("error") if e.response is not None else str(e)
        return json.dumps({"ok": False, "error": err, "detail": str(e)})
    except Exception as e:
        logger.exception("slack_channel_admin failed: %s", e)
        return json.dumps({"ok": False, "error": str(e)})


def _telegram_api(method: str, body: Dict[str, Any]) -> Dict[str, Any]:
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is not set"}
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token)}/{method}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
            parsed = json.loads(raw)
            return parsed
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}", "detail": str(e)}
    except Exception as e:
        logger.exception("telegram API %s failed: %s", method, e)
        return {"ok": False, "error": str(e)}


def _telegram_forum_topic_handler(args: dict, **kw) -> str:
    action = (args.get("action") or "").strip().lower()
    valid = frozenset(("create", "edit", "delete", "close", "reopen"))
    if action not in valid:
        return json.dumps({"error": f"action must be one of: {', '.join(sorted(valid))}"})

    _ensure_dotenv()

    chat_id = args.get("chat_id")
    if chat_id is None or str(chat_id).strip() == "":
        return json.dumps({"error": "chat_id is required (forum supergroup numeric id)"})

    try:
        chat_id_int = int(chat_id)
    except (TypeError, ValueError):
        return json.dumps({"error": "chat_id must be an integer (e.g. -1003348811704)"})

    thread_id: Optional[int] = None
    raw_thread = args.get("message_thread_id")
    if raw_thread is not None and str(raw_thread).strip() != "":
        try:
            thread_id = int(raw_thread)
        except (TypeError, ValueError):
            return json.dumps({"error": "message_thread_id must be an integer when provided"})

    if action != "create" and thread_id is None:
        return json.dumps(
            {"error": "message_thread_id is required for edit, delete, close, and reopen"}
        )

    method_body: tuple[str, Dict[str, Any]]

    if action == "create":
        name = (args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "name is required for create"})
        payload: Dict[str, Any] = {"chat_id": chat_id_int, "name": name}
        icon = args.get("icon_custom_emoji_id")
        if icon is not None and str(icon).strip():
            payload["icon_custom_emoji_id"] = str(icon).strip()
        method_body = ("createForumTopic", payload)
    elif action == "edit":
        payload = {"chat_id": chat_id_int, "message_thread_id": thread_id}
        new_name = args.get("name")
        if new_name is not None and str(new_name).strip():
            payload["name"] = str(new_name).strip()
        icon = args.get("icon_custom_emoji_id")
        if icon is not None and str(icon).strip():
            payload["icon_custom_emoji_id"] = str(icon).strip()
        if len(payload) <= 2:
            return json.dumps(
                {"error": "edit requires at least one of name or icon_custom_emoji_id"}
            )
        method_body = ("editForumTopic", payload)
    elif action == "delete":
        method_body = (
            "deleteForumTopic",
            {"chat_id": chat_id_int, "message_thread_id": thread_id},
        )
    elif action == "close":
        method_body = (
            "closeForumTopic",
            {"chat_id": chat_id_int, "message_thread_id": thread_id},
        )
    else:
        method_body = (
            "reopenForumTopic",
            {"chat_id": chat_id_int, "message_thread_id": thread_id},
        )

    method, body = method_body
    result = _telegram_api(method, body)
    return json.dumps(result)


SLACK_CHANNEL_ADMIN_SCHEMA = {
    "name": "slack_channel_admin",
    "description": (
        "Create, rename, or archive a Slack channel using the bot token (conversations.create / "
        "rename / archive). Requires OAuth scopes channels:manage and groups:write as "
        "appropriate. For multi-workspace tokens, pass team_id. Use when organizing the workspace; "
        "avoid destructive actions without user intent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "rename", "archive"],
                "description": "Operation to perform.",
            },
            "name": {
                "type": "string",
                "description": "Channel name for **create** (with or without #; normalized to Slack rules).",
            },
            "new_name": {
                "type": "string",
                "description": "New name for **rename**.",
            },
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID (e.g. C…); required for **rename** and **archive**.",
            },
            "is_private": {
                "type": "boolean",
                "description": "If true, create a private channel (**create** only). Default false.",
            },
            "team_id": {
                "type": "string",
                "description": "Optional workspace team id (T…) when the bot is in multiple workspaces.",
            },
        },
        "required": ["action"],
    },
}

TELEGRAM_FORUM_TOPIC_SCHEMA = {
    "name": "telegram_forum_topic",
    "description": (
        "Create or manage a **Telegram forum topic** (Bot API forum topic methods). "
        "**chat_id** must be a forum-enabled supergroup (numeric id, often negative). "
        "Private chats and non-forum groups are not valid. Use **message_thread_id** for "
        "edit/delete/close/reopen. Prefer when splitting long-running discussions by topic."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "edit", "delete", "close", "reopen"],
                "description": "Forum topic operation.",
            },
            "chat_id": {
                "type": "integer",
                "description": "Forum supergroup chat id (e.g. -100…).",
            },
            "name": {
                "type": "string",
                "description": "Topic name (**create**); optional new name for **edit**.",
            },
            "message_thread_id": {
                "type": "integer",
                "description": "Forum topic thread id; required for edit, delete, close, reopen.",
            },
            "icon_custom_emoji_id": {
                "type": "string",
                "description": "Optional custom emoji id for **create** or **edit**.",
            },
        },
        "required": ["action", "chat_id"],
    },
}

from tools.registry import registry

registry.register(
    name="slack_channel_admin",
    toolset="slack_workspace_admin",
    schema=SLACK_CHANNEL_ADMIN_SCHEMA,
    handler=_slack_channel_admin_handler,
    check_fn=_check_slack_token,
    requires_env=["SLACK_BOT_TOKEN"],
    emoji="💼",
)

registry.register(
    name="telegram_forum_topic",
    toolset="telegram_forum_admin",
    schema=TELEGRAM_FORUM_TOPIC_SCHEMA,
    handler=_telegram_forum_topic_handler,
    check_fn=_check_telegram_token,
    requires_env=["TELEGRAM_BOT_TOKEN"],
    emoji="📌",
)
