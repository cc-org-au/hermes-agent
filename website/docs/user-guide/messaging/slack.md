---
sidebar_position: 4
title: "Slack"
description: "Set up Hermes Agent as a Slack bot using Socket Mode"
---

# Slack Setup

Connect Hermes Agent to Slack as a bot using Socket Mode. Socket Mode uses WebSockets instead of
public HTTP endpoints, so your Hermes instance doesn't need to be publicly accessible — it works
behind firewalls, on your laptop, or on a private server.

:::warning Classic Slack Apps Deprecated
Classic Slack apps (using RTM API) were **fully deprecated in March 2025**. Hermes uses the modern
Bolt SDK with Socket Mode. If you have an old classic app, you must create a new one following
the steps below.
:::

## Overview

| Component | Value |
|-----------|-------|
| **Library** | `slack-bolt` / `slack_sdk` for Python (Socket Mode) |
| **Connection** | WebSocket — no public URL required |
| **Auth tokens needed** | Bot Token (`xoxb-`) + App-Level Token (`xapp-`) |
| **User identification** | Slack Member IDs (e.g., `U01ABC2DEF3`) |

---

## Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Enter an app name (e.g., "Hermes Agent") and select your workspace
5. Click **Create App**

You'll land on the app's **Basic Information** page.

---

## Step 2: Configure Bot Token Scopes

Navigate to **Features → OAuth & Permissions** in the sidebar. Scroll to **Scopes → Bot Token Scopes** and add the following:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages as the bot |
| `app_mentions:read` | Detect when @mentioned in channels |
| `channels:history` | Read messages in public channels the bot is in |
| `channels:read` | List and get info about public channels |
| `groups:history` | Read messages in private channels the bot is invited to |
| `im:history` | Read direct message history |
| `im:read` | View basic DM info |
| `im:write` | Open and manage DMs |
| `users:read` | Look up user information |
| `files:write` | Upload files (images, audio, documents) |

**Strongly recommended for channel coverage:**

| Scope | Purpose |
|-------|---------|
| `channels:join` | Lets the bot **join public channels on its own** (used by `hermes slack join-public`). Without it you must `/invite @Bot` in every channel. |

:::caution Missing scopes = missing features
Without `channels:history` and `groups:history`, the bot **will not receive messages in channels** —
it will only work in DMs. These are the most commonly missed scopes.
:::

**Optional scopes:**

| Scope | Purpose |
|-------|---------|
| `groups:read` | List and get info about private channels |
| `channels:manage` | Create, rename, and archive **public** channels (used by `SlackAdapter.create_channel` / `rename_channel` / `archive_channel`) |
| `groups:write` | Create and manage **private** channels the bot is allowed to manage |

After adding channel-management scopes, **reinstall the app** to the workspace and refresh `SLACK_BOT_TOKEN` in `~/.hermes/.env`.

---

## Step 3: Enable Socket Mode

Socket Mode lets the bot connect via WebSocket instead of requiring a public URL.

1. In the sidebar, go to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. You'll be prompted to create an **App-Level Token**:
   - Name it something like `hermes-socket` (the name doesn't matter)
   - Add the **`connections:write`** scope
   - Click **Generate**
4. **Copy the token** — it starts with `xapp-`. This is your `SLACK_APP_TOKEN`

:::tip
You can always find or regenerate app-level tokens under **Settings → Basic Information → App-Level Tokens**.
:::

---

## Step 4: Subscribe to Events

This step is critical — it controls what messages the bot can see.


1. In the sidebar, go to **Features → Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Expand **Subscribe to bot events** and add:

| Event | Required? | Purpose |
|-------|-----------|---------|
| `message.im` | **Yes** | Bot receives direct messages |
| `message.channels` | **Yes** | Bot receives messages in **public** channels it's added to |
| `message.groups` | **Recommended** | Bot receives messages in **private** channels it's invited to |
| `app_mention` | **Yes** | Required when the bot is @mentioned in channels — Slack often delivers `app_mention` (with or without a parallel `message` event). Hermes handles both and deduplicates. |

4. Click **Save Changes** at the bottom of the page

:::danger Missing event subscriptions is the #1 setup issue
If the bot works in DMs but **not in channels**, you almost certainly forgot to add
`message.channels` (for public channels) and/or `message.groups` (for private channels).
Without these events, Slack simply never delivers channel messages to the bot.
:::


---

## Step 5: Enable the Messages Tab

This step enables direct messages to the bot. Without it, users see **"Sending messages to this app has been turned off"** when trying to DM the bot.

1. In the sidebar, go to **Features → App Home**
2. Scroll to **Show Tabs**
3. Toggle **Messages Tab** to ON
4. Check **"Allow users to send Slash commands and messages from the messages tab"**

:::danger Without this step, DMs are completely blocked
Even with all the correct scopes and event subscriptions, Slack will not allow users to send direct messages to the bot unless the Messages Tab is enabled. This is a Slack platform requirement, not a Hermes configuration issue.
:::

---

## Step 6: Install App to Workspace

1. In the sidebar, go to **Settings → Install App**
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. After authorization, you'll see a **Bot User OAuth Token** starting with `xoxb-`
5. **Copy this token** — this is your `SLACK_BOT_TOKEN`

:::tip
If you change scopes or event subscriptions later, you **must reinstall the app** for the changes
to take effect. The Install App page will show a banner prompting you to do so.
:::

---

## Step 7: Find User IDs for the Allowlist

Hermes uses Slack **Member IDs** (not usernames or display names) for the allowlist.

To find a Member ID:

1. In Slack, click on the user's name or avatar
2. Click **View full profile**
3. Click the **⋮** (more) button
4. Select **Copy member ID**

Member IDs look like `U01ABC2DEF3`. You need your own Member ID at minimum.

---

## Step 8: Configure Hermes

Add the following to your `~/.hermes/.env` file:

```bash
# Required
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
SLACK_ALLOWED_USERS=U01ABC2DEF3              # Comma-separated Member IDs

# Optional
SLACK_HOME_CHANNEL=C01234567890              # Default channel for cron/scheduled messages
SLACK_HOME_CHANNEL_NAME=general              # Human-readable name for the home channel (optional)
```

Or run the interactive setup:

```bash
hermes gateway setup    # Select Slack when prompted
```

### Optional: App configuration token (`xoxe`)

Slack [app configuration tokens](https://api.slack.com/authentication/config-tokens) are **developer** tokens for manifest APIs — they are **not** your bot token (`xoxb`) or Socket Mode app token (`xapp`). Generate one under [api.slack.com/apps](https://api.slack.com/apps) → **Your App Configuration Tokens** → **Generate Token**, then set `SLACK_CONFIG_TOKEN` in the environment (or `.env`).

```bash
hermes slack config-test              # auth.test for the configuration token
hermes slack manifest-validate        # validate Hermes' built-in Socket Mode manifest
hermes slack manifest-export --app-id A0123456789   # export your app's current manifest (JSON)
hermes slack manifest-update --app-id A0123456789 --confirm   # apply Hermes manifest (reinstall app after)
```

**Duplicate an existing app (e.g. clone “Hermes Agent” for an operator instance):** export uses the same `SLACK_CONFIG_TOKEN` (or alias `SLACK_MANIFEST_KEY` in `.env`). From Basic Information, copy the **App ID** (`A…`) of the source app, then:

```bash
hermes slack manifest-clone --source-app-id A0XXXXXXXX --new-name "hermes-operator"
```

This calls `apps.manifest.export` → `apps.manifest.validate` → `apps.manifest.create`. The new app gets a distinct **display name** and **bot display name** (override with `--bot-display-name`). The manifest includes a default **OAuth redirect URL** (`https://localhost/slack/oauth_redirect`) so Slack’s authorize link can resolve `redirect_uri` (Hermes uses Socket Mode and does not host an OAuth callback — you still copy **xoxb** / **xapp** from the app settings after install). Save the printed **credentials** JSON, install to the workspace, then add **new** `SLACK_BOT_TOKEN` (xoxb) and `SLACK_APP_TOKEN` (xapp) for that app to the Hermes profile `.env` you use for the operator.

**Two Slack developer accounts:** App configuration tokens (xoxe) are per login. To clone an app that was created under account A but **create** the duplicate under account B, generate **two** tokens at [api.slack.com/apps](https://api.slack.com/apps) (each while signed into the right Slack account), then set in `.env`:

- `SLACK_CONFIG_TOKEN_DROPLET` — token for the account that can **export** the source app (manages the original app).
- `SLACK_CONFIG_TOKEN_OPERATOR` — token for the account that should **own** the new app (`validate` + `create` use this).

If both are set, Hermes uses droplet for export only and operator for validate/create. If neither is set, a single `SLACK_CONFIG_TOKEN` / `SLACK_MANIFEST_KEY` is used for all three steps (same account).

**`redirect_uri did not match any configured URIs`:** Slack requires every `redirect_uri` on `https://slack.com/oauth/v2/authorize` to be listed under the app’s **OAuth & Permissions → Redirect URLs**. Easiest fix: open [api.slack.com/apps](https://api.slack.com/apps) → your app → **OAuth & Permissions** → **Install to Workspace** (uses Slack’s internal flow). Or append a matching query parameter to your install link, e.g. `&redirect_uri=https%3A%2F%2Flocalhost%2Fslack%2Foauth_redirect`. To register the default URL and optionally rename the bot user in the manifest:

```bash
hermes slack manifest-patch-oauth --app-id A0123456789 --bot-display-name hermes --confirm
```

Repeat `--redirect-url https://…` to add more redirect URLs.

Configuration tokens **expire** (about 12 hours); rotate with Slack’s refresh flow. After `manifest-update`, **reinstall** the app to the workspace and refresh `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` in Hermes.

Then start the gateway:

```bash
hermes gateway              # Foreground
hermes gateway install      # Install as a user service
sudo hermes gateway install --system   # Linux only: boot-time system service
```

---

## Step 9: Get the Bot Into Channels

**Public channels — automatic (recommended):**

1. Add the **`channels:join`** bot scope (Step 2), then **reinstall** the app to the workspace.
2. On the machine where Hermes runs (with `SLACK_BOT_TOKEN` loaded from `~/.hermes/.env`):

```bash
hermes slack join-public
```

This calls the Slack Web API to **join every public channel** the bot is not already in. Re-run it after new public channels are created.

`hermes slack join-public --dry-run` lists channels it would join (still needs a valid token to list channels).

**Private channels** still require a manual invite — Slack does not allow bots to self-join private channels:

```
/invite @Hermes Agent
```

**Without `channels:join`:** invite the bot yourself in each channel (`/invite @YourBotName`).

---

## How the Bot Responds

Understanding how Hermes behaves in different contexts:

| Context | Behavior |
|---------|----------|
| **DMs** | Bot responds to every message — no @mention needed |
| **Channels** | Bot **only responds when @mentioned** (e.g., `@Hermes Agent what time is it?`). In channels, Hermes replies in a thread attached to that message. |
| **Threads** | If you @mention Hermes inside an existing thread, it replies in that same thread. |

:::tip
In channels, always @mention the bot. Simply typing a message without mentioning it will be ignored.
This is intentional — it prevents the bot from responding to every message in busy channels.
:::

---

## Configuration Options

Beyond the required environment variables from Step 8, you can customize Slack bot behavior through `~/.hermes/config.yaml`.

### Thread & Reply Behavior

```yaml
platforms:
  slack:
    # Controls how multi-part responses are threaded
    # "off"   — never thread replies to the original message
    # "first" — first chunk threads to user's message (default)
    # "all"   — all chunks thread to user's message
    reply_to_mode: "first"

    extra:
      # Whether to reply in a thread (default: true).
      # When false, channel messages get direct channel replies instead
      # of threads. Messages inside existing threads still reply in-thread.
      reply_in_thread: true

      # Also post thread replies to the main channel
      # (Slack's "Also send to channel" feature).
      # Only the first chunk of the first reply is broadcast.
      reply_broadcast: false
```

| Key | Default | Description |
|-----|---------|-------------|
| `platforms.slack.reply_to_mode` | `"first"` | Threading mode for multi-part messages: `"off"`, `"first"`, or `"all"` |
| `platforms.slack.extra.reply_in_thread` | `true` | When `false`, channel messages get direct replies instead of threads. Messages inside existing threads still reply in-thread. |
| `platforms.slack.extra.reply_broadcast` | `false` | When `true`, thread replies are also posted to the main channel. Only the first chunk is broadcast. |

### Session Isolation

```yaml
# Global setting — applies to Slack and all other platforms
group_sessions_per_user: true
```

When `true` (the default), each user in a shared channel gets their own isolated conversation session. Two people talking to Hermes in `#general` will have separate histories and contexts.

Set to `false` if you want a collaborative mode where the entire channel shares one conversation session. Be aware this means users share context growth and token costs, and one user's `/reset` clears the session for everyone.

### Mention & Trigger Behavior

```yaml
slack:
  # Require @mention in channels (this is the default behavior;
  # the Slack adapter enforces @mention gating in channels regardless,
  # but you can set this explicitly for consistency with other platforms)
  require_mention: true

  # Custom mention patterns that trigger the bot
  # (in addition to the default @mention detection)
  mention_patterns:
    - "hey hermes"
    - "hermes,"

  # Text prepended to every outgoing message
  reply_prefix: ""
```

:::info
Unlike Discord and Telegram, Slack does not have a `free_response_channels` equivalent. The Slack adapter always requires `@mention` in channels — this is hardcoded behavior. In DMs, the bot always responds without needing a mention.
:::

### Unauthorized User Handling

```yaml
slack:
  # What happens when an unauthorized user (not in SLACK_ALLOWED_USERS) DMs the bot
  # "pair"   — prompt them for a pairing code (default)
  # "ignore" — silently drop the message
  unauthorized_dm_behavior: "pair"
```

You can also set this globally for all platforms:

```yaml
unauthorized_dm_behavior: "pair"
```

The platform-specific setting under `slack:` takes precedence over the global setting.

### Voice Transcription

```yaml
# Global setting — enable/disable automatic transcription of incoming voice messages
stt_enabled: true
```

When `true` (the default), incoming audio messages are automatically transcribed using the configured STT provider before being processed by the agent.

### Full Example

```yaml
# Global gateway settings
group_sessions_per_user: true
unauthorized_dm_behavior: "pair"
stt_enabled: true

# Slack-specific settings
slack:
  require_mention: true
  unauthorized_dm_behavior: "pair"

# Platform config
platforms:
  slack:
    reply_to_mode: "first"
    extra:
      reply_in_thread: true
      reply_broadcast: false
```

---


## Home Channel

Set `SLACK_HOME_CHANNEL` to a channel ID where Hermes will deliver scheduled messages,
cron job results, and other proactive notifications. To find a channel ID:

1. Right-click the channel name in Slack
2. Click **View channel details**
3. Scroll to the bottom — the Channel ID is shown there

```bash
SLACK_HOME_CHANNEL=C01234567890
```

Make sure the bot has been **invited to the channel** (`/invite @Hermes Agent`).

---

## Push notifications for bot replies

Slack often **does not push-notify** for plain bot messages in DMs, even when your prefs say “all messages.” Hermes can prepend a **user mention** (`<@U…>`) to outbound text so Slack classifies the message as an **@mention** (which respects your mention notification settings).

**Default behavior (recommended):** enabled. Applies to:

- Replies in **DMs** / group DMs (`chat_type` = `dm`) — mentions the member who messaged the bot (first chunk only).
- Messages sent to **`SLACK_HOME_CHANNEL`** (e.g. cron output to your bot DM) — mentions **`SLACK_NOTIFY_USER_ID`** if set, otherwise the **first** id in **`SLACK_ALLOWED_USERS`**.

Disable if you dislike the visible `@you` prefix:

```bash
SLACK_NOTIFY_WITH_USER_MENTION=false
```

Override who gets mentioned for home-channel-only traffic:

```bash
SLACK_NOTIFY_USER_ID=U01ABCDEF12
```

---

## Multi-Workspace Support

Hermes can connect to **multiple Slack workspaces** simultaneously using a single gateway instance. Each workspace is authenticated independently with its own bot user ID.

### Configuration

Provide multiple bot tokens as a **comma-separated list** in `SLACK_BOT_TOKEN`:

```bash
# Multiple bot tokens — one per workspace
SLACK_BOT_TOKEN=xoxb-workspace1-token,xoxb-workspace2-token,xoxb-workspace3-token

# A single app-level token is still used for Socket Mode
SLACK_APP_TOKEN=xapp-your-app-token
```

Or in `~/.hermes/config.yaml`:

```yaml
platforms:
  slack:
    token: "xoxb-workspace1-token,xoxb-workspace2-token"
```

### OAuth Token File

In addition to tokens in the environment or config, Hermes also loads tokens from an **OAuth token file** at:

```
~/.hermes/platforms/slack/slack_tokens.json
```

This file is a JSON object mapping team IDs to token entries:

```json
{
  "T01ABC2DEF3": {
    "token": "xoxb-workspace-token-here",
    "team_name": "My Workspace"
  }
}
```

Tokens from this file are merged with any tokens specified via `SLACK_BOT_TOKEN`. Duplicate tokens are automatically deduplicated.

### How it works

- The **first token** in the list is the primary token, used for the Socket Mode connection (AsyncApp).
- Each token is authenticated via `auth.test` on startup. The gateway maps each `team_id` to its own `WebClient` and `bot_user_id`.
- When a message arrives, Hermes uses the correct workspace-specific client to respond.
- The primary `bot_user_id` (from the first token) is used for backward compatibility with features that expect a single bot identity.

---

## Voice Messages

Hermes supports voice on Slack:

- **Incoming:** Voice/audio messages are automatically transcribed using the configured STT provider: local `faster-whisper`, Groq Whisper (`GROQ_API_KEY`), or OpenAI Whisper (`VOICE_TOOLS_OPENAI_KEY`)
- **Outgoing:** TTS responses are sent as audio file attachments

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond to DMs | Verify `message.im` is in your event subscriptions and the app is reinstalled |
| Bot works in DMs but not in channels | **Most common issue.** Add `message.channels` and `message.groups` to event subscriptions, reinstall the app, and invite the bot to the channel with `/invite @Hermes Agent` |
| Bot doesn't respond to @mentions in channels | 1) Check `message.channels` event is subscribed. 2) Bot must be invited to the channel. 3) Ensure `channels:history` scope is added. 4) Reinstall the app after scope/event changes. 5) Slack often sends labelled mentions (`<@U123` then a display-name suffix) — Hermes matches those as well as plain `<@U123>`. |
| Slack stops working while WhatsApp/Telegram still fine | If you use a **shell watchdog**, it must **not** require every platform to be `connected`. When WhatsApp is `fatal`/`reconnecting`, Slack can still be healthy. Use `hermes gateway watchdog-check` (exit 0 = OK): it checks a **live `gateway.pid` process**, `gateway_state=running`, and **≥1** `connected` platform. See [Gateway watchdog](./gateway-watchdog). |
| Bot ignores messages in private channels | Add both the `message.groups` event subscription and `groups:history` scope, then reinstall the app and `/invite` the bot |
| "Sending messages to this app has been turned off" in DMs | Enable the **Messages Tab** in App Home settings (see Step 5) |
| DMs delivered (reactions/seen) but **no AI reply** | Hermes is almost certainly treating you as **unauthorized**. Confirm `SLACK_ALLOWED_USERS` in `$HERMES_HOME/.env` lists your **Member ID** (`U…` from Profile → ⋮ → Copy member ID) with **no spaces** after commas. If you see a pairing message, run `hermes pairing approve slack <code>` on the **same host** that runs the gateway. Use `hermes slack whoami` on that host to confirm the bot’s `bot_user_id` for @mentions in channels. |
| Want the bot in **every public channel** | Add **`channels:join`**, reinstall the app, then run `hermes slack join-public` (see Step 9). Private channels still need `/invite`. |
| "not_authed" or "invalid_auth" errors | Regenerate your Bot Token and App Token, update `.env` |
| Bot responds but can't post in a channel | Invite the bot to the channel with `/invite @Hermes Agent` |
| "missing_scope" error | Add the required scope in OAuth & Permissions, then **reinstall** the app |
| Socket disconnects frequently | Check your network; Bolt auto-reconnects but unstable connections cause lag |
| Changed scopes/events but nothing changed | You **must reinstall** the app to your workspace after any scope or event subscription change |

### Quick Checklist

If the bot isn't working in channels, verify **all** of the following:

1. ✅ `message.channels` event is subscribed (for public channels)
2. ✅ `message.groups` event is subscribed (for private channels)
3. ✅ `app_mention` event is subscribed
4. ✅ `channels:history` scope is added (for public channels)
5. ✅ `groups:history` scope is added (for private channels)
6. ✅ App was **reinstalled** after adding scopes/events
7. ✅ Bot was **invited** to the channel (`/invite @Hermes Agent`)
8. ✅ You are **@mentioning** the bot in your message

---

## Security

:::warning
**Always set `SLACK_ALLOWED_USERS`** with the Member IDs of authorized users. Without this setting,
the gateway will **deny all messages** by default as a safety measure. Never share your bot tokens —
treat them like passwords.
:::

- Tokens should be stored in `~/.hermes/.env` (file permissions `600`)
- Rotate tokens periodically via the Slack app settings
- Audit who has access to your Hermes config directory
- Socket Mode means no public endpoint is exposed — one less attack surface
