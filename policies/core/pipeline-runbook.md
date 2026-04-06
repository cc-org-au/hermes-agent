<!-- policy-read-order-nav:top -->
> **Governance read order** — step 10 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [README.md](../README.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Pipeline runbook (agents)

<!--
  Prerequisites (do not skip): read [`core/README.md`](README.md) — both runbooks,
  then [`deployment-handoff.md`](deployment-handoff.md). This script only validates files and
  refreshes indexes; it does not replace that context.
-->

**Run from the repository root** after the two runbooks and [`deployment-handoff.md`](deployment-handoff.md). The pipeline verifies/indexes policies and (when runtime roots are provided) materializes runtime outputs in the correct locations:

Do not pre-create runtime workspace trees or runtime-editable policy output trees manually before this pipeline run; treat pipeline materialization as the source of truth for initial structure.

## VPS hardening gate (lockout-safe, generic)

When this pipeline is used alongside VPS setup/hardening work, apply this gate before any SSH/firewall/authentication change:

- open and keep one verified SSH session active throughout hardening
- open and keep a provider console session active too when available
- treat any SSH listener, firewall, root-login, or auth-mode change as lockout-risking
- pause and require explicit operator confirmation before each lockout-risking step
- keep at least one verified existing access path active until a new path is proven in a fresh session
- validate connectivity on old and new SSH paths before removing the old path
- never assume provider console recovery exists; require verified recovery/admin paths first
- do not persist privileged credentials on-host as the only recovery copy
- do not disable fallback channels until the operator confirms they can still access the host
- treat console/recovery as potentially unavailable; if lockout occurs, assume rebuild may be required
- require two independently validated admin routes before removing/changing either route
- require pre-armed rollback automation before SSH daemon restart after auth/listener edits
- require explicit `AuthenticationMethods` in final SSH policy (no implicit `any`)
- require fresh non-multiplexed auth validation before proceeding:
  - key-only login fails
  - key+password login succeeds

Documented recovery verification example (after SSH listener recovery):

```text
LISTEN 0      128                        0.0.0.0:40227      0.0.0.0:*    users:(("sshd",pid=9352,fd=3))
LISTEN 0      128                           [::]:40227         [::]:*    users:(("sshd",pid=9352,fd=4))
```

Treat this as evidence format only: always capture the current listener output from the target host and attach it to the change record before proceeding.

## Runtime watchdog gate (recommended)

After pipeline materialization and before declaring messaging runtime "production ready":

- install a boot-started watchdog daemon under the runtime user context
- require watchdog health checks to validate both gateway runtime state and per-platform connected state
- require a bounded recovery ladder (restart -> diagnostics/fix -> restart)
- require anti-thrash controls (exponential backoff, jitter, rolling attempt window, cooldown)
- require append-only watchdog logs with UTC timestamps
- verify watchdog and gateway survive reboot without operator-attached shells

```bash
python policies/core/scripts/start_pipeline.py --dry-run   # validate only (writes nothing)
python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"
```

Or:

```bash
./policies/start_pipeline.sh --dry-run
./policies/start_pipeline.sh
```

Legacy optional mode (operations-only bootstrap):

```bash
python policies/core/scripts/start_pipeline.py --init-operations
```

**What it does**

1. **Strict verification** — required layout; every `policies/core/governance/standards/*.md` must contain an activation-prompt heading (so policies cannot silently pass as empty stubs).
2. **Regenerates** `policies/INDEX.md`.
3. **Writes** `policies/.pipeline_state/manifest.json` (gitignored) to detect future edits.
4. **Materializes canonical runtime policies** under `AGENT_HOME/policies` when `--policy-root` (or `AGENT_POLICY_ROOT`) is provided.
5. **Materializes runtime-editable outputs** under `AGENT_HOME/workspace` when `--workspace-root` (or `AGENT_WORKSPACE_ROOT`) is provided:
   - **`operations/`** — registers and project trees (`init_operations_stubs.py`)
   - **`policies/core/governance/generated/`** — generated governance markdown
   - **`policies/core/runtime/agent/`** — nested copy of the runtime agent pack (same as repo layout)
   - **Workspace root (flat)** — copies `BOOTSTRAP.md`, `AGENTS.md`, and the rest of the runtime pack `*.md` files to the **top level** of the workspace directory so operators and Hermes see entry points without deep paths; writes **`WORKSPACE.md`** describing these paths
6. **`--write-governance-md PATH`** (optional) — renders `scripts/templates/hermes_home_governance.md` with `{{WORKSPACE_ROOT}}` and `{{POLICY_ROOT}}` filled in (e.g. set `PATH` to `$HERMES_HOME/.hermes.md` so the agent receives path wiring via `agent/prompt_builder.py`).

For Hermes, use **`scripts/core/materialize_policies_into_hermes_home.sh`** after setting `HERMES_HOME`; it runs the pipeline with workspace + policy roots and governance stub generation.

**Tests:** `pytest tests/agent/test_prompt_builder.py` (context loading); policy verification runs inside `start_pipeline.py`.

## Droplet remediation backlog (REM) — operator notes

| ID | Topic | Repo / operator action |
|----|--------|-------------------------|
| REM-001 | SSH on `40227` (`sshd`) | **Preferred fix (repo):** `scripts/core/harden_ssh_management_port_tailscale.sh` — firewall so only Tailscale IPv4/IPv6 + `tailscale0` reach the port; **dry-run** by default, `sudo REM001_APPLY=1` to apply. Persist with `iptables-persistent` / `netfilter-persistent` after a **fresh Tailscale SSH test**. Still **do not** bind only `127.0.0.1` on the sole remote path without OOB recovery. **Unfinished:** rule must be applied **on the VPS with root**; IPv6 off or non-standard Tailscale interfaces need `REM001_*` env overrides. |
| REM-003 | Channel / workspace allowlists | Hermes: optional env `TELEGRAM_ALLOWED_CHATS`, `DISCORD_ALLOWED_CHANNELS`, `DISCORD_ALLOWED_GUILDS`, `SLACK_ALLOWED_CHANNELS`, `SLACK_ALLOWED_TEAMS`, `WHATSAPP_ALLOWED_CHATS` (comma-separated immutable IDs). Non-DM surfaces only; DMs still use user allowlists / pairing. |
| REM-005 | Log file `664` → `600` | `scripts/core/gateway-watchdog.sh` sets `chmod 600` on `$HERMES_HOME/logs/gateway-watchdog.log` when the runtime user owns it. Other log paths: operator `find` + `chmod` as owner or sudo. |
| REM-006 | Security foundation roles (9) | **Registers:** `scripts/templates/rem_operations/SECURITY_SUBAGENTS_REGISTER.md` → materialized to `workspace/operations/` via `scripts/core/materialize_rem_operations.sh` (also invoked from `materialize_policies_into_hermes_home.sh`). **Unfinished:** no per-role Hermes delegate profiles or cron automation shipped; operators use Chief sessions + canonical security standard. |
| REM-007 | Functional Directors | **Register:** `FUNCTIONAL_DIRECTORS_REGISTER.md` — all four slots **DORMANT** until workload criteria met. **Unfinished:** activation is a manual org decision + `ORG_CHART.md` update. |
| REM-009 | Project Lead `agentic-company` (AG-005) | **Register:** `PROJECT_LEADS_REGISTER.md` + `operations/projects/agentic-company/README.md`. **Unfinished:** optional dedicated delegate profile / long-lived agent process not created automatically. |
| Post-activation B | Gateway watchdog | Official script: `scripts/core/gateway-watchdog.sh` — health = `hermes gateway watchdog-check` (live `gateway.pid`, `gateway_state=running`, messaging rules per `gateway/status.py`: **default** ≥1 platform `connected`; **strict** all configured platforms `connected` if `messaging.watchdog_require_all_platforms` or `HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS` — see `policies/core/gateway-watchdog.md`). Recovery prefers `systemctl --user restart hermes-gateway-<profile>.service`, then `gateway run --replace` + `doctor --fix`, with backoff and attempt caps; logs append to `$HERMES_HOME/logs/gateway-watchdog.log`. |

**Full read sequence:** [`../README.md`](../README.md) (layer map & step tables) · scripts: [`scripts/README.md`](scripts/README.md).

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/security-prompts.md](security-prompts.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
