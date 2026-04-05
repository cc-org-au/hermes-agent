"""
Slack platform adapter.

Uses slack-bolt (Python) with Socket Mode for:
- Receiving messages from channels and DMs
- Sending responses back
- Handling slash commands
- Thread support
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

try:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_sdk.web.async_client import AsyncWebClient
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    AsyncApp = Any
    AsyncSocketModeHandler = Any
    AsyncWebClient = Any

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    SUPPORTED_DOCUMENT_TYPES,
    cache_document_from_bytes,
)


logger = logging.getLogger(__name__)


def _normalize_slack_socket_event(body: Any, event: Any) -> Dict[str, Any]:
    """Copy the inner event and backfill fields Slack omits on Socket Mode.

    Bolt injects ``event`` from ``body["event"]`` in normal cases, but kwargs
    injection can yield ``None`` for some Socket Mode / middleware paths. If so,
    fall back to ``body["event"]`` so we never process an empty dict (that
    would drop every message silently).

    Also backfills ``team`` from the envelope when the inner event omits it,
    so ``_team_bot_user_ids`` resolves correctly for mention checks and API
    clients in multi-workspace setups.
    """
    raw: Optional[Dict[str, Any]] = None
    if isinstance(event, dict) and event:
        raw = dict(event)
    elif isinstance(body, dict):
        inner = body.get("event")
        if isinstance(inner, dict) and inner:
            raw = dict(inner)
    if not raw:
        return {}
    out = raw
    team = (out.get("team") or out.get("team_id") or "").strip()
    if not team and isinstance(body, dict):
        team = (body.get("team_id") or "").strip()
        if not team:
            for auth in body.get("authorizations") or []:
                if isinstance(auth, dict):
                    tid = (auth.get("team_id") or "").strip()
                    if tid:
                        team = tid
                        break
    if team and not out.get("team"):
        out["team"] = team
    return out


def _slack_aggregate_visible_text(event: dict) -> str:
    """Combine top-level ``text`` with Block Kit plain_text / mrkdwn strings.

    Some clients leave ``text`` empty while @mentions live only under
    ``blocks``; channel mention-gating would otherwise drop the message.
    """
    chunks: List[str] = []
    t = event.get("text")
    if isinstance(t, str) and t.strip():
        chunks.append(t)

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 28:
            return
        if isinstance(obj, dict):
            if obj.get("type") in ("plain_text", "mrkdwn"):
                tx = obj.get("text")
                if isinstance(tx, str) and tx.strip():
                    chunks.append(tx)
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)

    blocks = event.get("blocks")
    if isinstance(blocks, list):
        walk(blocks, 0)

    return " ".join(chunks)


def check_slack_requirements() -> bool:
    """Check if Slack dependencies are available."""
    return SLACK_AVAILABLE


def _slash_command_socket_ack_fix_out(request_body: Any, dispatched: Any, ack: Any) -> Any:
    """Prefer ``ack.response`` for slash commands when Bolt ignored it (Socket Mode).

    slack-bolt's ``AsyncioListenerRunner`` with ``process_before_response=False`` returns
    the middleware ``response`` object whenever it is non-None, even after the listener
    calls ``ack()``. For Socket Mode slash commands, that wrong body can produce a
    ``payload`` Slack rejects with ``invalid_command_response``. Hermes always acks
    slash commands with an empty body (envelope-only); this restores that behavior.
    """
    if not isinstance(request_body, dict) or "command" not in request_body:
        return dispatched
    if ack is None:
        return dispatched
    ack_resp = getattr(ack, "response", None)
    if ack_resp is None:
        return dispatched
    return ack_resp


_HERMES_SLACK_ASYNCIO_RUNNER_PATCHED = False


def _ensure_slack_bolt_slash_socket_ack_fix() -> None:
    """Monkey-patch Bolt's async listener runner once (process-wide)."""
    global _HERMES_SLACK_ASYNCIO_RUNNER_PATCHED
    if _HERMES_SLACK_ASYNCIO_RUNNER_PATCHED:
        return
    try:
        from slack_bolt.listener.asyncio_runner import AsyncioListenerRunner
    except ImportError:
        return

    _orig = AsyncioListenerRunner.run

    async def _run(self, request, response, listener_name, listener, starting_time=None):
        out = await _orig(self, request, response, listener_name, listener, starting_time)
        try:
            return _slash_command_socket_ack_fix_out(
                getattr(request, "body", None),
                out,
                getattr(request.context, "ack", None),
            )
        except Exception:
            logger.debug("[Slack] slash ack fix wrapper failed (non-fatal)", exc_info=True)
            return out

    AsyncioListenerRunner.run = _run  # type: ignore[assignment]
    _HERMES_SLACK_ASYNCIO_RUNNER_PATCHED = True


class SlackAdapter(BasePlatformAdapter):
    """
    Slack bot adapter using Socket Mode.

    Requires two tokens:
      - SLACK_BOT_TOKEN (xoxb-...) for API calls
      - SLACK_APP_TOKEN (xapp-...) for Socket Mode connection

    Features:
      - DMs and channel messages (mention-gated in channels)
      - Thread support
      - File/image/audio attachments
      - Slash commands (/hermes and /hermes-<subcommand>)
      - Typing indicators (not natively supported by Slack bots)
    """

    MAX_MESSAGE_LENGTH = 39000  # Slack API allows 40,000 chars; leave margin

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.SLACK)
        self._app: Optional[AsyncApp] = None
        self._handler: Optional[AsyncSocketModeHandler] = None
        self._bot_user_id: Optional[str] = None
        self._user_name_cache: Dict[str, str] = {}  # user_id → display name
        self._socket_mode_task: Optional[asyncio.Task] = None
        # Multi-workspace support
        self._team_clients: Dict[str, AsyncWebClient] = {}   # team_id → WebClient
        self._team_bot_user_ids: Dict[str, str] = {}          # team_id → bot_user_id
        self._channel_team: Dict[str, str] = {}                # channel_id → team_id
        # When Slack sends both message + app_mention for one @mention, process once.
        self._slack_duplicate_ts: Dict[str, float] = {}
        # team_id:channel_id -> True if conversations.info says im or mpim (Slack sometimes omits channel_type).
        self._channel_dm_flags_cache: Dict[str, bool] = {}

    def _slack_is_duplicate_delivery(self, dedup_key: str) -> bool:
        """Return True if this team/channel/ts was handled moments ago."""
        now = time.monotonic()
        stale = [k for k, t in self._slack_duplicate_ts.items() if now - t > 15.0]
        for k in stale:
            self._slack_duplicate_ts.pop(k, None)
        if dedup_key in self._slack_duplicate_ts:
            return True
        self._slack_duplicate_ts[dedup_key] = now
        return False

    async def connect(self) -> bool:
        """Connect to Slack via Socket Mode."""
        if not SLACK_AVAILABLE:
            logger.error(
                "[Slack] slack-bolt not installed. Run: pip install slack-bolt",
            )
            return False

        raw_token = self.config.token
        app_token = os.getenv("SLACK_APP_TOKEN")

        if not raw_token:
            logger.error("[Slack] SLACK_BOT_TOKEN not set")
            return False
        if not app_token:
            logger.error("[Slack] SLACK_APP_TOKEN not set")
            return False

        # Support comma-separated bot tokens for multi-workspace
        bot_tokens = [t.strip() for t in raw_token.split(",") if t.strip()]

        # Also load tokens from OAuth token file
        from hermes_constants import get_hermes_home
        tokens_file = get_hermes_home() / "slack_tokens.json"
        if tokens_file.exists():
            try:
                saved = json.loads(tokens_file.read_text(encoding="utf-8"))
                for team_id, entry in saved.items():
                    tok = entry.get("token", "") if isinstance(entry, dict) else ""
                    if tok and tok not in bot_tokens:
                        bot_tokens.append(tok)
                        team_label = entry.get("team_name", team_id) if isinstance(entry, dict) else team_id
                        logger.info("[Slack] Loaded saved token for workspace %s", team_label)
            except Exception as e:
                logger.warning("[Slack] Failed to read %s: %s", tokens_file, e)

        try:
            _ensure_slack_bolt_slash_socket_ack_fix()
            # Acquire scoped lock to prevent duplicate app token usage
            from gateway.status import acquire_scoped_lock
            self._token_lock_identity = app_token
            acquired, existing = acquire_scoped_lock('slack-app-token', app_token, metadata={'platform': 'slack'})
            if not acquired:
                owner_pid = existing.get('pid') if isinstance(existing, dict) else None
                message = f'Slack app token already in use' + (f' (PID {owner_pid})' if owner_pid else '') + '. Stop the other gateway first.'
                logger.error('[%s] %s', self.name, message)
                self._set_fatal_error('slack_token_lock', message, retryable=False)
                return False

            # First token is the primary — used for AsyncApp / Socket Mode
            primary_token = bot_tokens[0]
            # Pass our module logger so Bolt unhandled-request WARNINGs and client
            # logs land in gateway.log alongside gateway.platforms.slack messages.
            async def _slack_before_authorize_logger(body, next_):
                # Runs before listeners — confirms Slack delivered something over Socket Mode.
                if os.getenv("SLACK_LOG_INBOUND", "").lower() in ("1", "true", "yes"):
                    if isinstance(body, dict):
                        ev = body.get("event") or {}
                        et = ev.get("type")
                        if et:
                            ch = str(ev.get("channel") or "")
                            tail = ch[-4:] if len(ch) >= 4 else ch
                            logger.info(
                                "[Slack] bolt envelope event type=%s subtype=%s channel=…%s",
                                et,
                                ev.get("subtype") or "",
                                tail,
                            )
                return await next_()

            self._app = AsyncApp(
                token=primary_token,
                logger=logger,
                before_authorize=_slack_before_authorize_logger,
            )

            # Register each bot token and map team_id → client
            for token in bot_tokens:
                client = AsyncWebClient(token=token)
                auth_response = await client.auth_test()
                team_id = auth_response.get("team_id", "")
                bot_user_id = auth_response.get("user_id", "")
                bot_name = auth_response.get("user", "unknown")
                team_name = auth_response.get("team", "unknown")

                self._team_clients[team_id] = client
                self._team_bot_user_ids[team_id] = bot_user_id

                # First token sets the primary bot_user_id (backward compat)
                if self._bot_user_id is None:
                    self._bot_user_id = bot_user_id

                logger.info(
                    "[Slack] Authenticated as @%s in workspace %s (team: %s)",
                    bot_name, team_name, team_id,
                )

            # Typos in SLACK_ALLOWED_USERS never match incoming user ids (silent deny in groups).
            allow_raw = os.getenv("SLACK_ALLOWED_USERS", "").strip()
            if allow_raw and allow_raw != "*":
                first_client = next(iter(self._team_clients.values()), None)
                if first_client is not None:
                    for uid in [x.strip() for x in allow_raw.split(",") if x.strip()]:
                        try:
                            r = await first_client.users_info(user=uid)
                            if not r.get("ok"):
                                logger.error(
                                    "[Slack] SLACK_ALLOWED_USERS id %r invalid in this workspace "
                                    "(users.info error=%s). Use Profile → … → Copy member ID.",
                                    uid,
                                    r.get("error"),
                                )
                        except Exception as e:
                            logger.warning(
                                "[Slack] Could not validate SLACK_ALLOWED_USERS=%r: %s",
                                uid,
                                e,
                            )

            # Use event("message") only. app.message("") relies on Bolt's text matcher,
            # which skips when event.text is empty — that can drop valid Socket Mode
            # payloads (blocks-only, some subtypes). event("message") still receives
            # those; dedupe remains on team/channel/ts.
            async def _route_incoming_slack_message(body, event, say):
                try:
                    normalized = _normalize_slack_socket_event(body, event)
                    if not normalized:
                        logger.warning(
                            "[Slack] Empty message event (body type=%s keys=%s event=%s)",
                            type(body).__name__,
                            list(body.keys()) if isinstance(body, dict) else None,
                            type(event).__name__,
                        )
                        return
                    await self._handle_slack_message(normalized)
                except Exception:
                    logger.exception("[Slack] Failed while routing message event")

            @self._app.error
            async def _slack_bolt_error_handler(error, logger):
                logger.exception("[Slack] Bolt listener error: %s", error)

            # Statement registration (not @-decorators): a @ line would attach to the
            # next function definition (e.g. app_mention), breaking Bolt wiring.
            self._app.event("message")(_route_incoming_slack_message)

            # Slack often delivers app_mention for @bot in channels. Some workspaces
            # or product configurations surface app_mention without a parallel
            # message event Hermes would otherwise see — handle both and dedupe.
            @self._app.event("app_mention")
            async def handle_app_mention(body, event, say):
                normalized = _normalize_slack_socket_event(body, event)
                if not normalized:
                    logger.warning(
                        "[Slack] Empty app_mention event (body keys=%s)",
                        list(body.keys()) if isinstance(body, dict) else None,
                    )
                    return
                await self._handle_slack_message(normalized)

            # Slash commands: /hermes and every /hermes-* from the Slack app manifest.
            # - One case-insensitive regex listener so Slack always matches after manifest changes.
            # - Socket Mode slash ack: send envelope only (no ``payload``). Slack validates
            #   HTTP-style bodies (``text`` / ``response_type``) and may return
            #   ``invalid_command_response``; see Socket Mode "Acknowledge events" + slash example.
            # - ``_ensure_slack_bolt_slash_socket_ack_fix()`` works around slack-bolt's async
            #   runner returning the middleware response instead of ``ack.response`` for slash
            #   commands when ``process_before_response=False`` (default).
            # - Run _handle_slash_command in a task so the ack returns immediately; the real
            #   reply is posted via the normal messaging path.
            _hermes_slash = re.compile(r"^/hermes(?:$|-(.+))$", re.IGNORECASE)

            async def _hermes_slash_router(ack, command):
                cmd_dict = dict(command) if isinstance(command, dict) else {}
                cmd_raw = (cmd_dict.get("command") or "").strip()
                cmd_norm = cmd_raw if cmd_raw.startswith("/") else f"/{cmd_raw}" if cmd_raw else ""
                m = _hermes_slash.match(cmd_norm.lower())
                if m and m.group(1):
                    suffix = m.group(1).strip()
                    rest = (cmd_dict.get("text") or "").strip()
                    cmd_dict["text"] = f"{suffix} {rest}".strip() if rest else suffix
                await ack()

                async def _slash_followup() -> None:
                    try:
                        await self._handle_slash_command(cmd_dict)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("[Slack] Slash command handler failed after ack")

                asyncio.create_task(_slash_followup())

            self._app.command(_hermes_slash)(_hermes_slash_router)

            # Start Socket Mode handler in background
            self._handler = AsyncSocketModeHandler(self._app, app_token)
            if os.getenv("SLACK_SOCKET_TRACE", "").lower() in ("1", "true", "yes"):
                try:
                    self._handler.client.trace_enabled = True
                except Exception:
                    logger.debug("[Slack] Could not enable SLACK_SOCKET_TRACE on client", exc_info=True)
            self._socket_mode_task = asyncio.create_task(self._handler.start_async())

            self._mark_connected()
            logger.info(
                "[Slack] Socket Mode connected (%d workspace(s))",
                len(self._team_clients),
            )
            logger.info(
                "[Slack] If messages never arrive: enable Event Subscriptions bot events "
                "(message.im, message.channels, message.groups, message.mpim, app_mention), "
                "add channels:history/groups:history, reinstall the app, and ensure only one "
                "active gateway per app (or set SLACK_LOG_INBOUND=1 to see bolt envelopes). "
                "Multiple Socket Mode connections receive load-balanced events."
            )
            return True

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("[Slack] Connection failed: %s", e, exc_info=True)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Slack."""
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception as e:  # pragma: no cover - defensive logging
                logger.warning("[Slack] Error while closing Socket Mode handler: %s", e, exc_info=True)
        self._mark_disconnected()

        # Release the token lock (use stored identity, not re-read env)
        try:
            from gateway.status import release_scoped_lock
            if getattr(self, '_token_lock_identity', None):
                release_scoped_lock('slack-app-token', self._token_lock_identity)
                self._token_lock_identity = None
        except Exception:
            pass

        logger.info("[Slack] Disconnected")

    def _get_client(self, chat_id: str) -> AsyncWebClient:
        """Return the workspace-specific WebClient for a channel."""
        team_id = self._channel_team.get(chat_id)
        if team_id and team_id in self._team_clients:
            return self._team_clients[team_id]
        return self._app.client  # fallback to primary

    def _slack_notify_mention_prefix(
        self,
        chat_id: str,
        metadata: Optional[Dict[str, Any]],
        *,
        chunk_index: int,
    ) -> str:
        """Prefix outgoing text with <@U…> so Slack treats the post as a highlight (push).

        Plain bot posts in IMs often do not respect \"all messages\" notification prefs;
        a user mention triggers the same path as @mentions.
        """
        if chunk_index != 0:
            return ""
        flag = os.getenv("SLACK_NOTIFY_WITH_USER_MENTION", "true").lower()
        if flag in ("0", "false", "no", "off"):
            return ""
        meta = metadata or {}
        uid = (meta.get("source_user_id") or "").strip()
        chat_type = (meta.get("source_chat_type") or "").strip().lower()
        mention = ""
        if uid and chat_type == "dm":
            mention = f"<@{uid}> "
        if not mention:
            home = os.getenv("SLACK_HOME_CHANNEL", "").strip()
            if home and str(chat_id) == home:
                notify_uid = os.getenv("SLACK_NOTIFY_USER_ID", "").strip()
                if not notify_uid:
                    raw = os.getenv("SLACK_ALLOWED_USERS", "").strip()
                    if raw and raw != "*":
                        notify_uid = raw.split(",")[0].strip()
                if notify_uid:
                    mention = f"<@{notify_uid}> "
        if not mention:
            return ""
        return mention

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to a Slack channel or DM."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        try:
            # Convert standard markdown → Slack mrkdwn
            formatted = self.format_message(content)

            # Split long messages, preserving code block boundaries
            chunks = self.truncate_message(formatted, self.MAX_MESSAGE_LENGTH)

            thread_ts = self._resolve_thread_ts(reply_to, metadata)
            last_result = None

            # reply_broadcast: also post thread replies to the main channel.
            # Controlled via platform config: gateway.slack.reply_broadcast
            broadcast = self.config.extra.get("reply_broadcast", False)

            for i, chunk in enumerate(chunks):
                text_out = chunk
                prefix = self._slack_notify_mention_prefix(chat_id, metadata, chunk_index=i)
                if prefix:
                    stripped = text_out.lstrip()
                    if not stripped.startswith("<@"):
                        text_out = prefix + text_out
                kwargs = {
                    "channel": chat_id,
                    "text": text_out,
                }
                if thread_ts:
                    kwargs["thread_ts"] = thread_ts
                    # Only broadcast the first chunk of the first reply
                    if broadcast and i == 0:
                        kwargs["reply_broadcast"] = True

                last_result = await self._get_client(chat_id).chat_postMessage(**kwargs)

            return SendResult(
                success=True,
                message_id=last_result.get("ts") if last_result else None,
                raw_response=last_result,
            )

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("[Slack] Send error: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e))

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
    ) -> SendResult:
        """Edit a previously sent Slack message."""
        if not self._app:
            return SendResult(success=False, error="Not connected")
        try:
            await self._get_client(chat_id).chat_update(
                channel=chat_id,
                ts=message_id,
                text=content,
            )
            return SendResult(success=True, message_id=message_id)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[Slack] Failed to edit message %s in channel %s: %s",
                message_id,
                chat_id,
                e,
                exc_info=True,
            )
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Show a typing/status indicator using assistant.threads.setStatus.

        Displays "is thinking..." next to the bot name in a thread.
        Requires the assistant:write or chat:write scope.
        Auto-clears when the bot sends a reply to the thread.
        """
        if not self._app:
            return

        thread_ts = None
        if metadata:
            thread_ts = metadata.get("thread_id") or metadata.get("thread_ts")

        if not thread_ts:
            return  # Can only set status in a thread context

        try:
            await self._get_client(chat_id).assistant_threads_setStatus(
                channel_id=chat_id,
                thread_ts=thread_ts,
                status="is thinking...",
            )
        except Exception as e:
            # Silently ignore — may lack assistant:write scope or not be
            # in an assistant-enabled context. Falls back to reactions.
            logger.debug("[Slack] assistant.threads.setStatus failed: %s", e)

    def _resolve_thread_ts(
        self,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolve the correct thread_ts for a Slack API call.

        Prefers metadata thread_id (the thread parent's ts, set by the
        gateway) over reply_to (which may be a child message's ts).

        When ``reply_in_thread`` is ``false`` in the platform extra config,
        top-level channel messages receive direct channel replies instead of
        thread replies.  Messages that originate inside an existing thread are
        always replied to in-thread to preserve conversation context.
        """
        # When reply_in_thread is disabled (default: True for backward compat),
        # only thread messages that are already part of an existing thread.
        if not self.config.extra.get("reply_in_thread", True):
            existing_thread = (metadata or {}).get("thread_id") or (metadata or {}).get("thread_ts")
            return existing_thread or None

        if metadata:
            if metadata.get("thread_id"):
                return metadata["thread_id"]
            if metadata.get("thread_ts"):
                return metadata["thread_ts"]
        return reply_to

    async def _upload_file(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Upload a local file to Slack."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        result = await self._get_client(chat_id).files_upload_v2(
            channel=chat_id,
            file=file_path,
            filename=os.path.basename(file_path),
            initial_comment=caption or "",
            thread_ts=self._resolve_thread_ts(reply_to, metadata),
        )
        return SendResult(success=True, raw_response=result)

    # ----- Markdown → mrkdwn conversion -----

    def format_message(self, content: str) -> str:
        """Convert standard markdown to Slack mrkdwn format.

        Protected regions (code blocks, inline code) are extracted first so
        their contents are never modified.  Standard markdown constructs
        (headers, bold, italic, links) are translated to mrkdwn syntax.
        """
        if not content:
            return content

        placeholders: dict = {}
        counter = [0]

        def _ph(value: str) -> str:
            """Stash value behind a placeholder that survives later passes."""
            key = f"\x00SL{counter[0]}\x00"
            counter[0] += 1
            placeholders[key] = value
            return key

        text = content

        # 1) Protect fenced code blocks (``` ... ```)
        text = re.sub(
            r'(```(?:[^\n]*\n)?[\s\S]*?```)',
            lambda m: _ph(m.group(0)),
            text,
        )

        # 2) Protect inline code (`...`)
        text = re.sub(r'(`[^`]+`)', lambda m: _ph(m.group(0)), text)

        # 3) Convert markdown links [text](url) → <url|text>
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: _ph(f'<{m.group(2)}|{m.group(1)}>'),
            text,
        )

        # 4) Convert headers (## Title) → *Title* (bold)
        def _convert_header(m):
            inner = m.group(1).strip()
            # Strip redundant bold markers inside a header
            inner = re.sub(r'\*\*(.+?)\*\*', r'\1', inner)
            return _ph(f'*{inner}*')

        text = re.sub(
            r'^#{1,6}\s+(.+)$', _convert_header, text, flags=re.MULTILINE
        )

        # 5) Convert bold: **text** → *text* (Slack bold)
        text = re.sub(
            r'\*\*(.+?)\*\*',
            lambda m: _ph(f'*{m.group(1)}*'),
            text,
        )

        # 6) Convert italic: _text_ stays as _text_ (already Slack italic)
        #    Single *text* → _text_ (Slack italic)
        text = re.sub(
            r'(?<!\*)\*([^*\n]+)\*(?!\*)',
            lambda m: _ph(f'_{m.group(1)}_'),
            text,
        )

        # 7) Convert strikethrough: ~~text~~ → ~text~
        text = re.sub(
            r'~~(.+?)~~',
            lambda m: _ph(f'~{m.group(1)}~'),
            text,
        )

        # 8) Convert blockquotes: > text → > text (same syntax, just ensure
        #    no extra escaping happens to the > character)
        # Slack uses the same > prefix, so this is a no-op for content.

        # 9) Restore placeholders in reverse order
        for key in reversed(list(placeholders.keys())):
            text = text.replace(key, placeholders[key])

        return text

    # ----- Reactions -----

    async def _add_reaction(
        self, channel: str, timestamp: str, emoji: str
    ) -> bool:
        """Add an emoji reaction to a message. Returns True on success."""
        if not self._app:
            return False
        try:
            await self._get_client(channel).reactions_add(
                channel=channel, timestamp=timestamp, name=emoji
            )
            return True
        except Exception as e:
            # Don't log as error — may fail if already reacted or missing scope
            logger.debug("[Slack] reactions.add failed (%s): %s", emoji, e)
            return False

    async def _remove_reaction(
        self, channel: str, timestamp: str, emoji: str
    ) -> bool:
        """Remove an emoji reaction from a message. Returns True on success."""
        if not self._app:
            return False
        try:
            await self._get_client(channel).reactions_remove(
                channel=channel, timestamp=timestamp, name=emoji
            )
            return True
        except Exception as e:
            logger.debug("[Slack] reactions.remove failed (%s): %s", emoji, e)
            return False

    # ----- User identity resolution -----

    async def _resolve_user_name(self, user_id: str, chat_id: str = "") -> str:
        """Resolve a Slack user ID to a display name, with caching."""
        if not user_id:
            return ""
        if user_id in self._user_name_cache:
            return self._user_name_cache[user_id]

        if not self._app:
            return user_id

        try:
            client = self._get_client(chat_id) if chat_id else self._app.client
            result = await client.users_info(user=user_id)
            user = result.get("user", {})
            # Prefer display_name → real_name → user_id
            profile = user.get("profile", {})
            name = (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("real_name")
                or user.get("name")
                or user_id
            )
            self._user_name_cache[user_id] = name
            return name
        except Exception as e:
            logger.debug("[Slack] users.info failed for %s: %s", user_id, e)
            self._user_name_cache[user_id] = user_id
            return user_id

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a local image file to Slack by uploading it."""
        try:
            return await self._upload_file(chat_id, image_path, caption, reply_to, metadata)
        except FileNotFoundError:
            return SendResult(success=False, error=f"Image file not found: {image_path}")
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[%s] Failed to send local Slack image %s: %s",
                self.name,
                image_path,
                e,
                exc_info=True,
            )
            text = f"🖼️ Image: {image_path}"
            if caption:
                text = f"{caption}\n{text}"
            return await self.send(chat_id, text, reply_to=reply_to, metadata=metadata)

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an image to Slack by uploading the URL as a file."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        try:
            import httpx

            # Download the image first
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(image_url)
                response.raise_for_status()

            result = await self._get_client(chat_id).files_upload_v2(
                channel=chat_id,
                content=response.content,
                filename="image.png",
                initial_comment=caption or "",
                thread_ts=self._resolve_thread_ts(reply_to, metadata),
            )

            return SendResult(success=True, raw_response=result)

        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(
                "[Slack] Failed to upload image from URL %s, falling back to text: %s",
                image_url,
                e,
                exc_info=True,
            )
            # Fall back to sending the URL as text
            text = f"{caption}\n{image_url}" if caption else image_url
            return await self.send(chat_id=chat_id, content=text, reply_to=reply_to)

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send an audio file to Slack."""
        try:
            return await self._upload_file(chat_id, audio_path, caption, reply_to, metadata)
        except FileNotFoundError:
            return SendResult(success=False, error=f"Audio file not found: {audio_path}")
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[Slack] Failed to send audio file %s: %s",
                audio_path,
                e,
                exc_info=True,
            )
            return SendResult(success=False, error=str(e))

    async def send_video(
        self,
        chat_id: str,
        video_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a video file to Slack."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        if not os.path.exists(video_path):
            return SendResult(success=False, error=f"Video file not found: {video_path}")

        try:
            result = await self._get_client(chat_id).files_upload_v2(
                channel=chat_id,
                file=video_path,
                filename=os.path.basename(video_path),
                initial_comment=caption or "",
                thread_ts=self._resolve_thread_ts(reply_to, metadata),
            )
            return SendResult(success=True, raw_response=result)

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[%s] Failed to send video %s: %s",
                self.name,
                video_path,
                e,
                exc_info=True,
            )
            text = f"🎬 Video: {video_path}"
            if caption:
                text = f"{caption}\n{text}"
            return await self.send(chat_id, text, reply_to=reply_to, metadata=metadata)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a document/file attachment to Slack."""
        if not self._app:
            return SendResult(success=False, error="Not connected")

        if not os.path.exists(file_path):
            return SendResult(success=False, error=f"File not found: {file_path}")

        display_name = file_name or os.path.basename(file_path)

        try:
            result = await self._get_client(chat_id).files_upload_v2(
                channel=chat_id,
                file=file_path,
                filename=display_name,
                initial_comment=caption or "",
                thread_ts=self._resolve_thread_ts(reply_to, metadata),
            )
            return SendResult(success=True, raw_response=result)

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[%s] Failed to send document %s: %s",
                self.name,
                file_path,
                e,
                exc_info=True,
            )
            text = f"📎 File: {file_path}"
            if caption:
                text = f"{caption}\n{text}"
            return await self.send(chat_id, text, reply_to=reply_to, metadata=metadata)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get information about a Slack channel."""
        if not self._app:
            return {"name": chat_id, "type": "unknown"}

        try:
            result = await self._get_client(chat_id).conversations_info(channel=chat_id)
            channel = result.get("channel", {})
            is_dm = channel.get("is_im", False)
            return {
                "name": channel.get("name", chat_id),
                "type": "dm" if is_dm else "group",
            }
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                "[Slack] Failed to fetch chat info for %s: %s",
                chat_id,
                e,
                exc_info=True,
            )
            return {"name": chat_id, "type": "unknown"}

    # ----- Internal handlers -----

    async def _conversation_is_dm_like(self, channel_id: str, team_id: str) -> bool:
        """True if channel is a 1:1 or group DM (not a normal public/private channel).

        When ``channel_type`` is omitted, ``G…`` ids are ambiguous (private channel vs
        mpim); ``conversations.info`` distinguishes them. Results are cached.
        """
        cache_key = f"{team_id}:{channel_id}"
        if cache_key in self._channel_dm_flags_cache:
            return self._channel_dm_flags_cache[cache_key]
        if not self._app:
            self._channel_dm_flags_cache[cache_key] = False
            return False
        try:
            client = self._team_clients.get(team_id) if team_id else None
            if client is None:
                client = self._app.client
            resp = await client.conversations_info(channel=channel_id)
            ch = resp.get("channel") or {}
            is_dm_like = bool(ch.get("is_im") or ch.get("is_mpim"))
            self._channel_dm_flags_cache[cache_key] = is_dm_like
            return is_dm_like
        except Exception as e:
            logger.warning(
                "[Slack] conversations.info failed for channel=%s: %s",
                channel_id,
                e,
            )
            self._channel_dm_flags_cache[cache_key] = False
            return False

    async def _handle_slack_message(self, event: dict) -> None:
        """Handle an incoming Slack message event."""
        # Ignore bot messages (including our own)
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        # Ignore message edits and deletions
        subtype = event.get("subtype")
        if subtype in ("message_changed", "message_deleted"):
            return

        raw_text = event.get("text", "") or ""
        if not isinstance(raw_text, str):
            raw_text = str(raw_text)
        aggregated = _slack_aggregate_visible_text(event)
        mention_haystack = aggregated if aggregated.strip() else raw_text

        text = raw_text
        user_id = event.get("user", "")
        channel_id = event.get("channel", "")
        ts = event.get("ts", "")
        team_id = event.get("team", "")

        if not user_id or not channel_id or not ts:
            logger.warning(
                "[Slack] Incomplete message event (user=%r channel=%r ts=%r) — ignoring",
                bool(user_id),
                bool(channel_id),
                bool(ts),
            )
            return

        dedup_key = f"{team_id}:{channel_id}:{ts}"
        if self._slack_is_duplicate_delivery(dedup_key):
            logger.debug("[Slack] Duplicate delivery suppressed for %s", dedup_key)
            return

        # Track which workspace owns this channel
        if team_id and channel_id:
            self._channel_team[channel_id] = team_id

        # Determine if this is a DM or channel message
        channel_type = (event.get("channel_type") or "").strip().lower()
        cid_u = str(channel_id).upper()
        # "im" = 1:1 DM, "mpim" = multi-person DM (channel id is usually G…).
        # Some Socket Mode payloads omit channel_type; 1:1 DM ids start with "D".
        # Without treating these as conversation-DMs, we'd require an @mention
        # that users rarely add in private chats.
        is_dm = channel_type in ("im", "mpim") or (
            not channel_type
            and channel_id
            and cid_u.startswith("D")
        )
        # G… can be a private channel or a group DM (mpim). If channel_type is
        # missing, resolve via API once per channel (cached).
        if not is_dm and not channel_type and channel_id and cid_u.startswith("G"):
            is_dm = await self._conversation_is_dm_like(channel_id, team_id)

        # Build thread_ts for session keying.
        # In channels: fall back to ts so each top-level @mention starts a
        #   new thread/session (the bot always replies in a thread).
        # In DMs: only use the real thread_ts — top-level DMs should share
        #   one continuous session, threaded DMs get their own session.
        if is_dm:
            thread_ts = event.get("thread_ts")  # None for top-level DMs
        else:
            thread_ts = event.get("thread_ts") or ts  # ts fallback for channels

        # In channels, only respond if the bot is @mentioned on top-level posts.
        # Thread replies use thread_ts != ts (Slack uses thread_ts == ts only for the
        # thread root); requiring a mention on every reply breaks normal conversations.
        bot_uid = self._team_bot_user_ids.get(team_id, self._bot_user_id)
        thread_ts_val = event.get("thread_ts")
        event_ts = event.get("ts")
        in_thread_reply = (
            thread_ts_val is not None
            and event_ts is not None
            and str(thread_ts_val) != str(event_ts)
        )
        if not is_dm and bot_uid and not in_thread_reply:
            # Slack may send `<@U123>` or `<@U123|displayname>` — substring
            # `in "<@U123>"` misses the latter.
            _mention_re = re.compile(
                rf"<@{re.escape(bot_uid)}(\|[^>]+)?>",
                re.IGNORECASE,
            )
            if not _mention_re.search(mention_haystack):
                logger.debug(
                    "[Slack] ignoring channel message (no bot mention in text/blocks) channel=%s",
                    channel_id,
                )
                return
            # Strip the bot mention from visible text (blocks or top-level)
            base = raw_text.strip() or aggregated
            text = _mention_re.sub("", base).strip()

        # Determine message type
        msg_type = MessageType.TEXT
        if text.startswith("/"):
            msg_type = MessageType.COMMAND

        # Handle file attachments
        media_urls = []
        media_types = []
        files = event.get("files", [])
        for f in files:
            mimetype = f.get("mimetype", "unknown")
            url = f.get("url_private_download") or f.get("url_private", "")
            if mimetype.startswith("image/") and url:
                try:
                    ext = "." + mimetype.split("/")[-1].split(";")[0]
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        ext = ".jpg"
                    # Slack private URLs require the bot token as auth header
                    cached = await self._download_slack_file(url, ext, team_id=team_id)
                    media_urls.append(cached)
                    media_types.append(mimetype)
                    msg_type = MessageType.PHOTO
                except Exception as e:  # pragma: no cover - defensive logging
                    logger.warning("[Slack] Failed to cache image from %s: %s", url, e, exc_info=True)
            elif mimetype.startswith("audio/") and url:
                try:
                    ext = "." + mimetype.split("/")[-1].split(";")[0]
                    if ext not in (".ogg", ".mp3", ".wav", ".webm", ".m4a"):
                        ext = ".ogg"
                    cached = await self._download_slack_file(url, ext, audio=True, team_id=team_id)
                    media_urls.append(cached)
                    media_types.append(mimetype)
                    msg_type = MessageType.VOICE
                except Exception as e:  # pragma: no cover - defensive logging
                    logger.warning("[Slack] Failed to cache audio from %s: %s", url, e, exc_info=True)
            elif url:
                # Try to handle as a document attachment
                try:
                    original_filename = f.get("name", "")
                    ext = ""
                    if original_filename:
                        _, ext = os.path.splitext(original_filename)
                        ext = ext.lower()

                    # Fallback: reverse-lookup from MIME type
                    if not ext and mimetype:
                        mime_to_ext = {v: k for k, v in SUPPORTED_DOCUMENT_TYPES.items()}
                        ext = mime_to_ext.get(mimetype, "")

                    if ext not in SUPPORTED_DOCUMENT_TYPES:
                        continue  # Skip unsupported file types silently

                    # Check file size (Slack limit: 20 MB for bots)
                    file_size = f.get("size", 0)
                    MAX_DOC_BYTES = 20 * 1024 * 1024
                    if not file_size or file_size > MAX_DOC_BYTES:
                        logger.warning("[Slack] Document too large or unknown size: %s", file_size)
                        continue

                    # Download and cache
                    raw_bytes = await self._download_slack_file_bytes(url, team_id=team_id)
                    cached_path = cache_document_from_bytes(
                        raw_bytes, original_filename or f"document{ext}"
                    )
                    doc_mime = SUPPORTED_DOCUMENT_TYPES[ext]
                    media_urls.append(cached_path)
                    media_types.append(doc_mime)
                    msg_type = MessageType.DOCUMENT
                    logger.debug("[Slack] Cached user document: %s", cached_path)

                    # Inject text content for .txt/.md files (capped at 100 KB)
                    MAX_TEXT_INJECT_BYTES = 100 * 1024
                    if ext in (".md", ".txt") and len(raw_bytes) <= MAX_TEXT_INJECT_BYTES:
                        try:
                            text_content = raw_bytes.decode("utf-8")
                            display_name = original_filename or f"document{ext}"
                            display_name = re.sub(r'[^\w.\- ]', '_', display_name)
                            injection = f"[Content of {display_name}]:\n{text_content}"
                            if text:
                                text = f"{injection}\n\n{text}"
                            else:
                                text = injection
                        except UnicodeDecodeError:
                            pass  # Binary content, skip injection

                except Exception as e:  # pragma: no cover - defensive logging
                    logger.warning("[Slack] Failed to cache document from %s: %s", url, e, exc_info=True)

        # Resolve user display name (cached after first lookup)
        user_name = await self._resolve_user_name(user_id, chat_id=channel_id)

        # Build source
        source = self.build_source(
            chat_id=channel_id,
            chat_name=channel_id,  # Will be resolved later if needed
            chat_type="dm" if is_dm else "group",
            user_id=user_id,
            user_name=user_name,
            thread_id=thread_ts,
            server_id=str(team_id) if team_id else None,
        )

        msg_event = MessageEvent(
            text=text,
            message_type=msg_type,
            source=source,
            raw_message=event,
            message_id=ts,
            media_urls=media_urls,
            media_types=media_types,
            reply_to_message_id=thread_ts if thread_ts != ts else None,
        )

        # Add 👀 reaction to acknowledge receipt
        await self._add_reaction(channel_id, ts, "eyes")

        await self.handle_message(msg_event)

        # Replace 👀 with ✅ when done
        await self._remove_reaction(channel_id, ts, "eyes")
        await self._add_reaction(channel_id, ts, "white_check_mark")

    async def _handle_slash_command(self, command: dict) -> None:
        """Handle /hermes slash command."""
        text = command.get("text", "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")
        team_id = command.get("team_id", "")

        # Track which workspace owns this channel
        if team_id and channel_id:
            self._channel_team[channel_id] = team_id

        # Map subcommands to gateway commands — derived from central registry.
        # Also keep "compact" as a Slack-specific alias for /compress.
        from hermes_cli.commands import slack_slack_subcommand_text_map
        subcommand_map = slack_slack_subcommand_text_map()
        first_word = text.split()[0] if text else ""
        if first_word in subcommand_map:
            # Preserve arguments after the subcommand
            rest = text[len(first_word):].strip()
            text = f"{subcommand_map[first_word]} {rest}".strip() if rest else subcommand_map[first_word]
        elif text:
            pass  # Treat as a regular question
        else:
            text = "/help"

        _cid_u = str(channel_id).upper()
        _slash_is_dm = _cid_u.startswith("D")
        source = self.build_source(
            chat_id=channel_id,
            chat_type="dm" if _slash_is_dm else "group",
            user_id=user_id,
            server_id=str(team_id) if team_id else None,
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.COMMAND if text.startswith("/") else MessageType.TEXT,
            source=source,
            raw_message=command,
        )

        await self.handle_message(event)

    async def _download_slack_file(self, url: str, ext: str, audio: bool = False, team_id: str = "") -> str:
        """Download a Slack file using the bot token for auth, with retry."""
        import asyncio
        import httpx

        bot_token = self._team_clients[team_id].token if team_id and team_id in self._team_clients else self.config.token
        last_exc = None

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    response = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {bot_token}"},
                    )
                    response.raise_for_status()

                    if audio:
                        from gateway.platforms.base import cache_audio_from_bytes
                        return cache_audio_from_bytes(response.content, ext)
                    else:
                        from gateway.platforms.base import cache_image_from_bytes
                        return cache_image_from_bytes(response.content, ext)
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 429:
                        raise
                    if attempt < 2:
                        logger.debug("Slack file download retry %d/2 for %s: %s",
                                     attempt + 1, url[:80], exc)
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise
        raise last_exc

    async def _download_slack_file_bytes(self, url: str, team_id: str = "") -> bytes:
        """Download a Slack file and return raw bytes, with retry."""
        import asyncio
        import httpx

        bot_token = self._team_clients[team_id].token if team_id and team_id in self._team_clients else self.config.token
        last_exc = None

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    response = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {bot_token}"},
                    )
                    response.raise_for_status()
                    return response.content
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 429:
                        raise
                    if attempt < 2:
                        logger.debug("Slack file download retry %d/2 for %s: %s",
                                     attempt + 1, url[:80], exc)
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise
        raise last_exc
