<!-- policy-read-order-nav:top -->
> **Governance read order** — step 5 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/deployment-handoff.md](deployment-handoff.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Messaging gateway watchdog (policy)

## Purpose

For **production** deployments where Hermes serves users through the **messaging gateway** (Telegram, Slack, Discord, WhatsApp, etc.), the operator MUST ensure **continuous gateway process uptime** and **at least one connected messaging adapter**, with **automated recovery** when the stack degrades.

This file is the **policies-layer** requirement. The full procedure, CLI semantics, script env vars, and logs are documented for operators in:

**[`website/docs/user-guide/messaging/gateway-watchdog.md`](../../website/docs/user-guide/messaging/gateway-watchdog.md)** (repository path: `website/docs/user-guide/messaging/gateway-watchdog.md`)

Implementation references in the Hermes Agent codebase:

- `gateway/status.py` — `runtime_status_watchdog_healthy()` (health rules)
- `hermes gateway watchdog-check` — exit 0 when healthy
- `scripts/gateway-watchdog.sh` — optional external supervisor loop

---

## Requirements

1. **Health definition** — External automation MUST use **`hermes gateway watchdog-check`** (or equivalent logic), not ad-hoc “all platforms connected” checks. Healthy means: valid **`gateway.pid`** process, **`gateway_state=running`** in `gateway_state.json`, and **≥1** platform with **`state=connected`**. Requiring every platform to be connected is **forbidden** for watchdog purposes (it causes unnecessary restarts when one bridge is flaky).

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
