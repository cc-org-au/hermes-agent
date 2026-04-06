<!-- policy-read-order-nav:top -->
> **Governance read order** — step 5 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/deployment-handoff.md](deployment-handoff.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Messaging gateway watchdog (policy)

## Purpose

For **production** deployments where Hermes serves users through the **messaging gateway** (Telegram, Slack, Discord, WhatsApp, etc.), the operator MUST ensure **continuous gateway process uptime** and **healthy messaging adapters** (default: **at least one** connected; optional **strict**: **every configured** platform connected), with **automated recovery** when the stack degrades.

This file is the **policies-layer** requirement. The full procedure, CLI semantics, script env vars, and logs are documented for operators in:

**[`website/docs/user-guide/messaging/gateway-watchdog.md`](../../website/docs/user-guide/messaging/gateway-watchdog.md)** (repository path: `website/docs/user-guide/messaging/gateway-watchdog.md`)

Implementation references in the Hermes Agent codebase:

- `gateway/status.py` — `runtime_status_watchdog_healthy()` (health rules)
- `hermes gateway watchdog-check` — exit 0 when healthy
- `scripts/core/gateway-watchdog.sh` — optional external supervisor loop

---

## Repeat implementation checklist (operators)

Use this when standing up or cloning a production gateway so **watchdog semantics** and **strict multi-channel** behavior match the reference deployment.

### 1. Choose health mode

| Mode | When to use | Config |
|------|-------------|--------|
| **Default** | At least one messaging adapter up is enough; one flaky bridge should not force restarts | (omit flag or set false) |
| **Strict** | Every configured platform (Slack, Telegram, WhatsApp, …) must be `connected` before `watchdog-check` passes | `messaging.watchdog_require_all_platforms: true` in merged gateway config, **or** `HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1` in the environment of `watchdog-check` / the watchdog script |

Strict mode is implemented in `gateway/status.py` (`_resolve_watchdog_require_all_platforms`, `GatewayConfig.get_connected_platforms()`). Env overrides config when set to a truthy/falsey string.

### 2. Merge config on the profile (`HERMES_HOME`)

Under the active profile (e.g. `~/.hermes/profiles/chief-orchestrator/config.yaml`), merge a `messaging` block without dropping existing keys:

```yaml
messaging:
  watchdog_require_all_platforms: true
```

The repo template `scripts/templates/chief-orchestrator-profile.example.yaml` documents the same block.

### 3. External supervisor

- Copy or symlink `scripts/core/gateway-watchdog.sh` per `website/docs/user-guide/messaging/gateway-watchdog.md`.
- Ensure the loop runs as the **same Unix user** as the gateway and with the same **`HERMES_HOME`** / **`-p <profile>`** as production.
- Optional env for automation: **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS`** (documented in the script header).

### 4. Verification

```bash
# From repo venv, profile explicit:
./venv/bin/python -m hermes_cli.main -p chief-orchestrator gateway watchdog-check && echo OK
```

- **Default:** success message indicates at least one connected platform.
- **Strict:** success message includes `all_connected=` listing every configured adapter (or passes with “no messaging platforms configured” if none are enabled).

### 5. Tests and docs (reimplementation in code)

- `tests/gateway/test_status.py` — strict vs default `runtime_status_watchdog_healthy` behavior
- `AGENTS.md` — gateway watchdog summary
- `website/docs/user-guide/messaging/gateway-watchdog.md` — operator-facing detail

### 6. VPS automation note

Non-interactive steps as **`hermesuser`** often use **`scripts/core/droplet_run.sh --droplet-require-sudo --sudo-user hermesuser '…'`** with **`SSH_SUDO_PASSWORD`** in the same **`~/.env/.env`** as **`SSH_*`** (see script headers). Use that for `git pull`, editing `config.yaml`, and `gateway restart` without delegating manual SSH to the operator when credentials are available.

---

## Requirements

1. **Health definition** — External automation MUST use **`hermes gateway watchdog-check`** (or equivalent logic). Healthy means: valid **`gateway.pid`** process, **`gateway_state=running`** in `gateway_state.json`, and messaging uptime per mode:
   - **Default:** **≥1** platform with **`state=connected`** (one flaky bridge does not fail the check).
   - **Strict (opt-in):** set **`messaging.watchdog_require_all_platforms: true`** in gateway config, or **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1`** in the environment. Then **every** platform returned by configured “connected” messaging settings must be **`state=connected`**; if none are configured, the check passes. Use strict mode only when the deployment requires **all** social channels up (e.g. Slack **and** Telegram **and** WhatsApp); it may restart more often if any single adapter reconnects slowly.

2. **Recovery** — When health checks fail repeatedly, automation MUST recover the gateway without spawning a **second** concurrent poller for the same tokens. Prefer **`systemctl --user restart hermes-gateway-<profile>.service`** when that unit exists for the active **`HERMES_HOME`** (e.g. **`chief-orchestrator`** after **`hermes gateway install`**). Otherwise use **`hermes gateway run --replace`**, then **`hermes doctor --fix`** followed by another restart/replace if the gateway does not recover. Rate-limit recovery attempts (backoff/cooldown) to avoid tight loops on misconfiguration.

3. **Logging** — Watchdog output MUST be appended to a durable log (e.g. `$HERMES_HOME/logs/gateway-watchdog.log` when using the stock script) for post-incident review.

4. **Alignment** — This operational policy complements [`unified-deployment-and-security.md`](unified-deployment-and-security.md) and channel/messaging governance; it does not replace security-first or deployment ordering. For **VPS** specifics (which Unix user runs the gateway, **`hermes -p chief-orchestrator`**, avoiding a second gateway under the admin SSH account, and post-deploy **`watchdog-check`**), read **Step 15 — VPS gateway** in that runbook. For **Slack Socket Mode slash commands** and **`invalid_command_response`**, read the **Slash commands (`/hermes-*`)** subsection under **Hermes + Slack (Socket Mode)** in the same file.

---

## Relation to governance

- **[`core/governance/standards/channel-architecture-policy.md`](core/governance/standards/channel-architecture-policy.md)** — channel design; the watchdog ensures the **runtime** gateway stays connected to configured platforms.
- **[`deployment-handoff.md`](deployment-handoff.md)** — builder handoff; after runtime is live, apply this policy for **always-on messaging** targets.

---

## Non-goals

- This policy does not mandate a specific process manager (systemd, tmux, cron); it mandates **observable health** and **documented recovery**.
- Single-user interactive CLI-only use may omit an external watchdog; **gateway-backed production** paths should not.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/README.md](README.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
