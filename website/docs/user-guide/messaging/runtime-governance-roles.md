---
sidebar_position: 3
title: "Runtime governance & messaging roles"
description: "Auto-inject workspace operations YAML into every agent; route Slack/Telegram/WhatsApp surfaces to org role personas without extra bots"
---

# Runtime governance and messaging roles

Hermes already loads `HERMES_HOME/.hermes.md` and the materialized `workspace/` pack into the system prompt. For **agentic-company** deployments, two more **on-disk** files make policy enforcement practical without pasting long activation prompts into every chat:

| File | Purpose |
|------|---------|
| `workspace/memory/runtime/operations/runtime_governance.runtime.yaml` | **Concise directives** (activation session pointer, role slug, bullet rules, paths to read with tools). Injected on **every new** agent (CLI + gateway). |
| `workspace/memory/runtime/operations/role_assignments.yaml` | **Per–role-slug** display name, required policy reads, optional `hermes_profile_for_delegation` hint for `delegate_task`. |

## Bootstrap from the repo

```bash
hermes workspace governance init     # copies examples if missing
hermes workspace governance path     # print absolute paths
hermes workspace governance show     # print key fields (sanitized)
```

Templates live in the git checkout: `scripts/templates/runtime_governance.runtime.example.yaml`, `scripts/templates/role_assignments.example.yaml`, and `scripts/templates/messaging_channel_role_map.example.yaml`.

### Sync routing from `.env` allowlists

After `workspace governance init`, edit `workspace/memory/runtime/operations/messaging_channel_role_map.yaml` (Slack `C…` → role slug, etc.), then:

```bash
hermes workspace governance sync-messaging   # writes role_assignments + messaging_role_routing.yaml
```

The gateway **merges** `workspace/memory/runtime/operations/messaging_role_routing.yaml` into `messaging.role_routing` on top of `config.yaml` (overlay wins for `channels` / `chats` / `threads` maps). Restart the gateway after syncing.

### Token-model §14 disclosure (automatic)

For human-visible messaging surfaces, the gateway appends a final line `--<Exact Role Name>` using the **Display name** from `role_assignments.yaml` for the routed role (streaming and non-streaming paths). Set `messaging.disclosure_line_append: false` in `config.yaml` to disable, or `messaging.disclosure_fallback_display_name` when role routing is off but you still want a fixed label.

### Singleton audit

- `hermes gateway audit-singleton` — list gateway-like PIDs and user `hermes-gateway*.service` units.
- `hermes doctor` includes a heuristic **multiple gateway process** warning.

Chief / HR (or IT automation) edit the YAML under **`HERMES_HOME`**; changes apply on the **next** new CLI session or the **next** gateway agent construction (gateway may reuse a cached agent per chat until `/new` / reset).

## Org profiles (Hermes `-p` isolation)

Role **manifest** profiles are created from `scripts/core/org_agent_profiles_manifest.yaml`:

```bash
hermes profile sync-org --dry-run    # preview
hermes profile sync-org              # create missing profiles
hermes profile sync-org --refresh-config   # re-merge toolsets / max_turns
```

Hard isolation (separate memories, `.env`, gateway) still requires **separate profiles** and usually **separate gateway units** per profile.

## One Slack bot, multiple *personas*

A single Slack app token cannot be shared across multiple live gateways. For **one** bot serving multiple **organizational personas**, map surfaces to **role slugs** in `config.yaml`:

```yaml
messaging:
  role_routing:
    enabled: true
    default_role: chief_orchestrator
    slack:
      channels:
        C0123456789: security_governor
      threads:
        "1234567890.123456": incident_lead
    telegram:
      chats:
        "-1001234567890": ops_lead
    whatsapp:
      chats:
        "12025550123@c.us": reception_bot
```

Resolution order: **thread** (if present) → **channel/chat id** → **`default_role`**. The gateway appends a short **ephemeral** block built from `role_assignments.yaml`. This is **prompt + disk policy** enforcement, not a second Slack app.

## IT / Security and the watchdog

Operators should run **`scripts/core/gateway-watchdog.sh`** (or systemd) under the **same** user as the gateway. With **`WATCHDOG_ENFORCE_SINGLE_GATEWAY=1`** (default), the loop removes duplicate gateway processes before each health check. Document ownership in your org register (e.g. IT/Security maintains watchdog + singleton policy; Chief edits governance YAML).

See also: [Gateway watchdog](./gateway-watchdog), [Messaging overview](./index).
