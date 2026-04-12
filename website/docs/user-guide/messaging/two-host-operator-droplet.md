---
sidebar_position: 8
title: "Operator + droplet: two isolated gateways"
description: "Run Hermes on a VPS and a Mac without cross-talk: WhatsApp sessions, lock instances, watchdogs, and Telegram/Slack"
---

# Two isolated gateways (operator Mac + droplet VPS)

This guide is for running **two Hermes deployments** that must **never** share live messaging sessions: one on a **Linux VPS** (droplet) and one on a **Mac** (operator workstation).

## Non-negotiable rules

1. **One Baileys (WhatsApp Web) session per phone number**  
   You cannot scan the same WhatsApp account on two servers. If both gateways used the **same** WhatsApp login, the second would kick the first offline.

2. **One Telegram bot token / one Slack app per live gateway**  
   Duplicate processes with the **same** `TELEGRAM_BOT_TOKEN` or `SLACK_BOT_TOKEN` will fight for a single connection (token lock / missed events).  
   **Options:** use **different** Telegram bots and Slack apps per host, **or** run Telegram/Slack only on the droplet and **disable** them on the operator profile.

3. **`HERMES_GATEWAY_LOCK_INSTANCE` is not a substitute for (1) and (2)**  
   It only separates **filesystem** lock paths under `$XDG_STATE_HOME/hermes/gateway-locks/` when you copy `HERMES_HOME` between machines. It does **not** split WhatsApp/Telegram/Slack provider sessions.

## Recommended WhatsApp split (your scenario)

| Host | WhatsApp account (QR session) | Mode | Purpose |
|------|------------------------------|------|--------|
| **Droplet** | **Business** number (e.g. `61483757391`) | `self-chat` | You message **yourself** on the business account; only the droplet gateway handles that thread. |
| **Operator Mac** | **Personal** number (e.g. `61419933874`) | `bot` | You chat **with your business contact** from the personal app; the operator gateway is logged in as **personal** and accepts DMs **from** the business JID. |

This uses **two different WhatsApp accounts**, so two Baileys sessions are valid at the same time.

### Droplet (`chief-orchestrator` profile) — business self-chat only

In **`HERMES_HOME/.env`** (profile or top-level merged env):

```bash
WHATSAPP_ENABLED=true
WHATSAPP_MODE=self-chat
# Only the business number may trigger non–self-chat paths; blocks DMs from your personal number.
WHATSAPP_ALLOWED_USERS=61483757391
```

In **`config.yaml`** (optional but recommended):

```yaml
whatsapp:
  unauthorized_dm_behavior: ignore
```

Pair the bridge with the **WhatsApp Business** app for `61483757391` (`hermes whatsapp` on the server).

If the gateway keeps sending **DM pairing codes** even though `WHATSAPP_ALLOWED_USERS` lists your business number, ensure `lid-mapping-*.json` under `HERMES_HOME/whatsapp/session` (or `platforms/whatsapp/session`) is present after pairing—Hermes resolves phone ↔ LID against those files—and that you are not mixing two different `HERMES_HOME` profiles for the same host.

### Operator Mac — personal inbox, business peer only

On the **operator** machine, use a **separate** `HERMES_HOME` (e.g. `~/.hermes/profiles/operator` or default `~/.hermes`).

```bash
WHATSAPP_ENABLED=true
WHATSAPP_MODE=bot
# Allow incoming messages whose sender is your business number (the contact you message from personal).
WHATSAPP_ALLOWED_USERS=61483757391
```

Pair with the **personal** WhatsApp (not Business). Hermes sees the DM thread with your business contact: messages **from** business (incoming) and messages **you send** from personal to business (your prompts are delivered to the gateway). Replies go back on that thread. No feedback loop with the droplet because the droplet is logged in as a **different** account.

The bridge tags **bot-mode** outbound text with an invisible sentinel so your own Hermes replies are not mistaken for new user prompts (loop-safe), in addition to message-id tracking. If you ever see echoes in self-chat, keep the default reply prefix (or raise `MIN_PREFIX_ECHO_LEN` in the bridge).

## Lock instance + service install (both hosts)

Set a **stable** label **before** `gateway install` and `gateway watchdog-install` so generated **systemd** units and **LaunchAgent** plists embed the variable:

```bash
# Droplet (example)
export HERMES_GATEWAY_LOCK_INSTANCE=droplet

# Operator Mac (example)
export HERMES_GATEWAY_LOCK_INSTANCE=operator
```

Then reinstall services so definitions refresh:

```bash
hermes -p <profile> gateway install --force
hermes -p <profile> gateway watchdog-install --force
```

Linux user units pick up `Environment=HERMES_GATEWAY_LOCK_INSTANCE=…` from the generator. macOS LaunchAgents include the same key under `EnvironmentVariables`.

## Watchdog (each host)

- **Droplet:** `hermes gateway watchdog-install` (or `scripts/core/install_and_restart_gateway_watchdog.sh`) + optional systemd user unit from `scripts/core/hermes-gateway-watchdog.user.service.example`. Ensure **one** watchdog per `HERMES_HOME`.
- **Operator:** `hermes gateway watchdog-install` on the Mac; use `hermes gateway audit-singleton` if anything looks duplicated.

## Verification

On each machine, with the correct profile:

```bash
hermes gateway audit-singleton
hermes gateway watchdog-check
```

Strict all-platform health (when enabled) requires every configured adapter connected — if the operator disables Telegram/Slack, ensure they are **disabled** in config so the watchdog does not expect them.

## Checklist summary

- [ ] Different **WhatsApp** QR logins (business on droplet, personal on operator).
- [ ] `WHATSAPP_ALLOWED_USERS` tuned so droplet does **not** accept personal-number DMs on the business inbox.
- [ ] Telegram/Slack: **disjoint tokens** or **disabled** on one host.
- [ ] `HERMES_GATEWAY_LOCK_INSTANCE` set and services reinstalled on **both** hosts.
- [ ] One gateway + one external watchdog per `HERMES_HOME` per machine.
