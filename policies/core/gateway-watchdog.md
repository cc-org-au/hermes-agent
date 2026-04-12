<!-- policy-read-order-nav:top -->
> **Governance read order** — step 5 of 56 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/deployment-handoff.md](deployment-handoff.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Messaging gateway watchdog (policy)

## Purpose

For **production** deployments where Hermes serves users through the **messaging gateway** (Telegram, Slack, Discord, WhatsApp, etc.), the operator MUST ensure **continuous gateway process uptime** and **automated recovery** when the stack degrades. Prefer **strict** health (every **configured** platform `connected`) via `messaging.watchdog_require_all_platforms`, **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS`**, or the stock **`scripts/core/gateway-watchdog.sh`** defaults so a single dropped channel (e.g. WhatsApp bridge exit) triggers recovery; use lenient **≥1 connected** only when intentionally tolerating a down bridge (e.g. staging) or when **two-host** setups share a token on one platform and that platform is disabled on the secondary host.

This file is the **policies-layer** requirement. The full procedure, CLI semantics, script env vars, and logs are documented for operators in:

**[`website/docs/user-guide/messaging/gateway-watchdog.md`](../../website/docs/user-guide/messaging/gateway-watchdog.md)** (repository path: `website/docs/user-guide/messaging/gateway-watchdog.md`)

Implementation references in the Hermes Agent codebase:

- `gateway/status.py` — `runtime_status_watchdog_healthy()` (health rules)
- `hermes gateway watchdog-check` — exit 0 when healthy
- `scripts/gateway-watchdog.sh` — optional external supervisor loop

---

## Requirements

1. **Health definition** — External automation MUST use **`hermes gateway watchdog-check`** (or equivalent logic), not ad-hoc checks. Minimum: valid **`gateway.pid`** process, **`gateway_state=running`**, and **≥1** platform **`state=connected`** (default CLI/config). **Strict** mode (every configured platform **`connected`**) is **recommended** for multi-channel production so a dropped adapter is treated as unhealthy; it is **not** forbidden. On **two hosts** with the **same** bot token on a platform, strict mode on both will surface token-lock failures until one host disables that platform or uses a distinct token.

2. **Recovery** — When health checks fail repeatedly, automation MUST attempt **`hermes gateway run --replace`**, then **`hermes doctor --fix`** followed by another replace if the gateway does not recover. Rate-limit recovery attempts (backoff/cooldown) to avoid tight loops on misconfiguration.

3. **Logging** — Watchdog output MUST be appended to a durable log (e.g. `$HERMES_HOME/logs/gateway-watchdog.log` when using the stock script) for post-incident review.

4. **Alignment** — This operational policy complements [`unified-deployment-and-security.md`](unified-deployment-and-security.md) and channel/messaging governance; it does not replace security-first or deployment ordering.

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
