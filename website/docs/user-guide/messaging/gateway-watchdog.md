---
sidebar_position: 2
title: "Gateway watchdog"
description: "Keep the messaging gateway and platform connections healthy with watchdog-check, scripts/core/gateway-watchdog.sh, doctor --fix, and recovery backoff"
---

# Gateway watchdog (uptime & recovery)

The messaging gateway is a long-lived process that should stay up and keep messaging adapters **healthy**. For servers or VPS deployments, run an **external watchdog** that periodically verifies health and recovers when something breaks.

## What “healthy” means

`hermes gateway watchdog-check` exits **0** only when all of the following are true:

| Check | Meaning |
|--------|--------|
| **Gateway process** | `gateway.pid` in `$HERMES_HOME` references a **live** Hermes gateway process. This avoids treating a crashed process as healthy when `gateway_state.json` is stale. |
| **Gateway state** | `gateway_state.json` has `gateway_state: running`. |
| **Messaging uptime** | Depends on mode (see below). |

### Default mode (≥1 connected)

Under `platforms`, **at least one** adapter has `state: connected`. Hermes does **not** require every platform to be connected in this mode. For example, Slack can be healthy while WhatsApp is `reconnecting` or `fatal`; the check still passes so a flaky bridge does not force restarts that tear down healthy adapters.

**CLI note:** `hermes gateway watchdog-check` uses this lenient rule **unless** you enable strict mode (below). **`scripts/core/gateway-watchdog.sh`** instead defaults to **strict** (`WATCHDOG_REQUIRE_ALL_PLATFORMS=1` → `HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1`) so the supervisor restarts the gateway when **any** configured platform is not `connected`. Set `WATCHDOG_REQUIRE_ALL_PLATFORMS=0` in the watchdog environment to match the lenient CLI behavior.

### Strict mode (all configured platforms connected)

When **`messaging.watchdog_require_all_platforms: true`** is set in merged gateway config (`config.yaml` / `gateway.json`), or when **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1`** is set in the environment (env overrides config when set to a truthy/falsey string), **every** messaging platform that Hermes considers **configured and enabled** for connection (`GatewayConfig.get_connected_platforms()`) must have `state: connected` in `gateway_state.json`. If **no** such platforms are configured, the check passes (nothing to enforce).

Use strict mode when you want the watchdog to recover until **Slack, Telegram, WhatsApp,** and any other configured channel are all up—not only one of them.

Run manually (from the repo with venv activated, `HERMES_HOME` set or `-p` for a named profile):

```bash
hermes gateway watchdog-check && echo OK
# e.g. chief-orchestrator profile on a VPS:
# hermes -p chief-orchestrator gateway watchdog-check && echo OK
```

## Coordination (no fighting with gateway control)

- **Singleton dedupe** (removing duplicate `gateway run` PIDs for this `HERMES_HOME`) is implemented in **`gateway.status.dedupe_gateway_processes_for_current_home`**. It runs **inside** **`hermes gateway watchdog-check`** (before health reads) and, in **`scripts/core/gateway-watchdog.sh`**, **once per loop** via the same Python entry point **before** `watchdog-check` (disable with **`WATCHDOG_DEDUPE_EACH_TICK=0`**). Do not add a separate shell loop that `pkill`s gateway processes — you would race systemd and duplicate `SIGTERM`s.
- **This shell watchdog** calls Hermes CLI for `watchdog-check`, optional `systemctl --user restart hermes-gateway-*.service`, `gateway run --replace`, and `doctor --fix`, plus that **one** Python dedupe import per interval. It does not `pkill` or `kill` gateway PIDs from shell.
- **systemd** may run **`hermes-gateway-<profile>.service`** (gateway process) and optionally **`hermes-gateway-watchdog.service`** (this loop). They are complementary: the gateway unit starts the daemon; the watchdog unit only **observes** health and **restarts** through supported commands when checks fail.

## Official shell watchdog

The repo ships `scripts/core/gateway-watchdog.sh`: a loop that:

1. Runs singleton dedupe for the current `HERMES_HOME` (Python; same logic as inside `watchdog-check`), unless **`WATCHDOG_DEDUPE_EACH_TICK=0`**.
2. Polls `watchdog-check` on a fixed interval while healthy (via `venv/bin/python -m hermes_cli.main`, with **`-p`** when `HERMES_HOME` is under `profiles/<name>`).
3. On failure: applies **exponential backoff + jitter**, then prefers **`systemctl --user`** recovery on the matching **`hermes-gateway-<name>.service`** unit when that file exists (same layout as `hermes gateway install`): stop the unit, clear current-home gateway PIDs + scoped locks via the Python helpers, `reset-failed`, then `start` the unit again. Only when no unit exists does it fall back to **`hermes gateway run --replace`** in the background.
4. If still unhealthy: runs **`hermes doctor --fix`** (append output to `$HERMES_HOME/logs/gateway-watchdog.log`), then restarts/replaces the gateway again.
5. Enforces a **rolling cap** on recovery attempts and a **cooldown** so a broken config does not spin forever.

**Orchestrator / VPS:** If `~/.hermes/profiles/chief-orchestrator` exists, the script defaults **`HERMES_HOME`** there (so logs and `gateway_state.json` match **`hermes -p chief-orchestrator`**). Override with **`HERMES_HOME`** or **`HERMES_WATCHDOG_PROFILE`** / **`HERMES_PROFILE_BASE`** when needed.

Copy it to `$HERMES_HOME/bin/gateway-watchdog.sh`, `chmod +x`, and run it under **systemd**, **tmux**, or a **cron** `@reboot` job as the **same user** that owns the gateway (so `HERMES_HOME` and `gateway.pid` match).

**SSH / automation:** Prefer `scripts/core/install_and_restart_gateway_watchdog.sh` (run as the gateway user from the repo checkout). It copies the watchdog into `$HERMES_HOME/bin`, stops prior **watchdog** processes whose argv contains that destination path (not a broad `pkill` of `gateway`), then starts one `nohup` process. Inlining `pkill -f gateway-watchdog` in a remote `bash -c '…'` often matches the supervisor’s own command line and drops the session before `nohup` runs — use the installer or match the full path.

**systemd user unit example:** `scripts/core/hermes-gateway-watchdog.user.service.example` — run **one** watchdog per `HERMES_HOME`; `flock` inside `gateway-watchdog.sh` prevents duplicate shell loops for the same profile.

### Environment variables

All variables are optional; defaults are in the script header.

- **`HERMES_HOME`** — Profile / instance directory (explicit; wins over auto profile pick).
- **`HERMES_PROFILE_BASE`** — Directory that contains `profiles/` (default `~/.hermes`).
- **`HERMES_WATCHDOG_PROFILE`** — Named profile under `profiles/<name>` when `HERMES_HOME` is not set.
- **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS`** — `1` / `0` / `true` / `false` forces strict or default messaging health for `watchdog-check`. When **unset**, uses **`messaging.watchdog_require_all_platforms`** from Hermes gateway config.
- **`WATCHDOG_REQUIRE_ALL_PLATFORMS`** — shorthand read by **`gateway-watchdog.sh`** only: default **`1`** (strict) unless **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS`** is already exported. Set **`0`** for lenient (≥1 connected) checks inside this loop.
- **`WATCHDOG_PREFER_SYSTEMD`** — `1` (default) to try `systemctl --user restart` when `~/.config/systemd/user/hermes-gateway-*.service` exists for that profile; set `0` to always use `gateway run --replace`.
- **`HERMES_AGENT_DIR`** — Path to the `hermes-agent` checkout containing `venv` (default `~/hermes-agent`).
- **`WATCHDOG_INTERVAL_SECONDS`** — Seconds between checks when healthy (default `60`).
- **`WATCHDOG_MAX_BACKOFF_SECONDS`**, **`WATCHDOG_JITTER_MAX_SECONDS`** — Backoff behavior between recovery attempts.
- **`WATCHDOG_MAX_ATTEMPTS_IN_WINDOW`**, **`WATCHDOG_ATTEMPT_WINDOW_SECONDS`**, **`WATCHDOG_COOLDOWN_SECONDS`** — Rate limiting after repeated failures.
- **`WATCHDOG_DEDUPE_EACH_TICK`** — `1` (default): run Python singleton dedupe at the **start** of each loop (before `watchdog-check`). Set `0` to rely on dedupe inside `watchdog-check` only.
- **`HERMES_GATEWAY_WATCHDOG_ENFORCE_SINGLE`** (alias **`WATCHDOG_ENFORCE_SINGLE_GATEWAY`**) — default **on**: `hermes gateway watchdog-check` runs this **before** reading health state and sends **`SIGTERM`** to **extra** gateway daemons for the **current** `HERMES_HOME`. Matching uses `hermes_cli.gateway.find_gateway_pids` (excluding `watchdog-check` / `audit-singleton`), then filters by **`HERMES_HOME`** from `/proc/<pid>/environ` when available, else by **`-p <profile>`** in argv. The PID registered in **`gateway.pid`** is kept when it is still live and matches; otherwise the **newest** matching process (by `/proc` start time on Linux) is kept. Set **`0`** to disable. External **`gateway-watchdog.sh`** loops should use the same variables so they do not fight the built-in check.
- **`WATCHDOG_SINGLE_INSTANCE_LOCK`** — `1` (default): take an exclusive **`flock`** on **`$HERMES_HOME/gateway-watchdog.lock`** at startup so two copies of **`gateway-watchdog.sh`** cannot run for the same **`HERMES_HOME`** (the second exits immediately). Set `0` to disable if your platform has no **`flock`** or you coordinate duplicates another way.

### Logs

The watchdog appends to:

```text
$HERMES_HOME/logs/gateway-watchdog.log
```

Inspect this file when diagnosing restart loops or `doctor --fix` output.

## Relation to systemd / `gateway install`

`hermes gateway install` sets up a service that starts the gateway at boot. The **shell watchdog** is an extra layer: it watches **runtime health** (process + `gateway_state.json` + messaging rules above) and recovers through the **same** service manager when possible:

| Host | Gateway service | Watchdog recovery (preferred) |
|------|-----------------|-------------------------------|
| **Linux** | `systemd --user` **`hermes-gateway-<profile>.service`** | **`systemctl --user restart`** that unit |
| **macOS** | **launchd** **`ai.hermes.gateway*.plist`** | **`launchctl kickstart`** for that label (see `scripts/core/gateway-watchdog.sh`) |

If no unit is installed, the watchdog falls back to **`hermes gateway run --replace`** plus **`doctor --fix`** as before. When a Linux user unit exists, the watchdog now keeps recovery **systemd-owned** instead of escaping into a detached replace process.

### macOS: `hermes gateway watchdog-install`

On the **operator Mac** (or any macOS host running the gateway under **`hermes gateway install`**), register **one** LaunchAgent for the external loop:

```bash
hermes -p chief-orchestrator gateway watchdog-install   # example profile
hermes gateway watchdog-start    # if not already running
```

This copies **`scripts/core/gateway-watchdog.sh`** to **`$HERMES_HOME/bin/`** and installs **`~/Library/LaunchAgents/ai.hermes.gateway-watchdog*.plist`**. Remove with **`hermes gateway watchdog-uninstall`**. Use **`hermes gateway audit-singleton`** to list gateway PIDs and launchd jobs.

**Do not** run the same messaging bot tokens on **two** machines (e.g. operator Mac **and** droplet VPS) — they will fight for Telegram/Slack/WhatsApp locks. Use separate credentials or only one live gateway.

Use both gateway **install** and **watchdog-install** if you need automatic recovery without manual SSH.

## See also

- **Policy layer (repository):** `policies/core/gateway-watchdog.md` — governance requirements for production messaging gateway uptime and recovery (read with the rest of `policies/`).
- [Messaging Gateway overview](/docs/user-guide/messaging) — architecture and setup
- [`hermes doctor`](/docs/reference/cli-commands#hermes-doctor) — diagnostics and `--fix`
- [Gateway internals](/docs/developer-guide/gateway-internals) — code layout
