<!-- policy-read-order-nav:top -->
> **Governance read order** — step 1 of 56 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** none — this is the **first** document in the sequence. Do not treat later policy files as valid context until this one is understood.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

<!--
  Read order within core/ (flat runbooks): (1) this file — security-first-setup.md
  (2) unified-deployment-and-security.md — full deployment runbook
  (3) deployment-handoff.md — builder/runtime handoff
  Former numeric prefixes: 0000 → this file; 000 → unified runbook; START_HERE → deployment-handoff.md
-->

# Security-first setup

## Purpose

This is the **first file to follow**.

Use it before deploying any policies, prompts, runtime agents, automations, or project workflows.

Its purpose is to help the human operator build a **secure, isolated agent environment** first, so that later deployment happens inside the correct security boundaries rather than trying to retrofit them afterward.

This file is the **human-first setup runbook**.

After completing this file, the next file in the order of operations is:

- `policies/core/unified-deployment-and-security.md`

Then:

- `policies/core/deployment-handoff.md` — drives deployment of the canonical policies, prompts, runbooks, operational records, bootstrap/agent markdown pack, and the runtime artifact trees (`AGENT_HOME/workspace/memory/runtime/operations/` and generated policy material under `AGENT_HOME/policies/core/governance/generated/`).

---

## Required Order of Operations

Follow this order exactly:

1. `policies/core/security-first-setup.md` (this file)
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md`
4. `policies/core/runtime/agent/BOOTSTRAP.md`
5. `policies/core/runtime/agent/AGENTS.md`
6. the remaining attached agent markdown files referenced by `BOOTSTRAP.md` and `AGENTS.md`

**Within this file (human setup before the policies pipeline):** finish the **environment** (Steps 1–8) → provision **isolated service accounts** and credentials the agent will use (Step 9) → place **deployment entry files** (Step 10) → keep integrations minimal (Step 11) → **validate** (Step 12). **After** `deployment-handoff.md`, when you are ready to verify and index the policy tree, run the pipeline described in [`policies/core/pipeline-runbook.md`](pipeline-runbook.md) (`start_pipeline.py`)—do not treat the pipeline as a substitute for the runbooks.

Do not skip directly to prompts or runtime activation before the environment is isolated and validated.

---

## High-Level Goal

You are setting up **two separate trust zones**:

### Zone A — Workstation (e.g. macOS)

Your real machine. This is the **more sensitive** system for the human operator.

Treat it as containing:

- your normal browser
- your password manager
- operator SSH keys and hardware tokens (when used)
- your important files
- your logged-in sessions

The **long-lived agent/gateway runtime must not run here** at the highest posture. Builder/editors may run here under a **non-admin** account; execution and integrations that define “runtime” belong on **Zone B**.

### Zone B — Runtime (dedicated VPS)

This is the **only** zone where the 24/7 agent, gateway, and automation-adjacent services should live.

Treat it as:

- network-separated from the workstation
- disposable or rebuildable (snapshots, IaC, images)
- tightly scoped
- **non-root for routine operation**
- workspace-only data layout
- browser-isolated (if a browser exists on the server)
- integration-constrained
- safe to wipe or restore from a known-good image

The runtime zone exists so a compromise there does **not** automatically become a compromise of your workstation vault, keys, and personal sessions—**smallest possible blast radius**.

**Optional alternative:** a **dedicated local guest VM** may stand in for a VPS if you enforce the same logical rules (separate non-sudo runtime user, no shared folders/clipboard with the workstation, no vault on the guest). The canonical path described here is **VPS-first**.

---

## Dedicated machine alternative (non-VPS)

If you choose a dedicated physical machine (or dedicated local host) instead of a VPS, apply the same hardening pattern before any runtime activation:

1. Use a clean OS install dedicated to agent runtime work only.
2. Keep a maintenance/admin account and a separate non-sudo runtime account.
3. Build private admin access first (tailnet/VPN), then verify login over private addressing.
4. Keep at least one active maintenance shell open during all lockout-risking changes.
5. Apply SSH hardening in checkpoints (key policy, root-login policy, listener policy), one change at a time.
6. Use deny-by-default host firewall and allow only required management/runtime paths.
7. Keep workstation isolation rules identical (no personal vault sync, no personal browser/session reuse on runtime host).
8. Record evidence after each checkpoint (effective SSH settings, listeners, firewall state, and fresh-session access tests).

Treat the host as disposable/rebuildable even when it is not cloud-managed: no step should assume recovery tooling is available.

---

## macOS account model (strongly recommended)

Use **separate macOS accounts** to separate privilege from daily use:

### Administrator account (bootstrap and maintenance only)

Use **only** for:

- creating the standard user account(s)
- macOS updates that require admin
- **initial VPS provisioning** (first SSH session, cloud-init, firewall baseline) when that step must run locally
- rare break-glass maintenance

**Rules:**

- **Do not** run the AI agent/gateway runtime on this account.
- **Do not** use this account for daily chat, email, or browsing tied to messaging platforms that control the agent.
- **Do not** treat this account as “normal work”—it exists to reduce time-at-high-privilege.

### Standard user account (daily operator)

Create a **fresh Standard user** (no membership in `admin`, no `sudo`) for:

- day-to-day work
- chat clients used to talk to the bot (Telegram, Slack, Discord, etc.) when that is your control path
- editors/builders (e.g. IDE) where the OS allows without elevation

**Rules:**

- **No sudo** for routine work—forces a deliberate switch to admin for anything that mutates the system.
- Prefer **no production SSH keys** on this account; if SSH to the VPS is unavoidable, use a **dedicated key**, passphrase-protected, and **separate** from automation/CI keys.
- **Prefer the chat → gateway → VPS path** for operations instead of routine interactive SSH from the laptop (reduces “message → shell” blast radius).

This split ensures **runtime and routine control-plane traffic** are not tied to an always-admin session on the Mac.

---

## VPS access and network posture (security-critical)

Assume the VPS has a **public IP**. Treat the network as **hostile** unless you explicitly overlay private access.

### Pre-hardening operator checkpoint (mandatory)

Before any SSH/firewall/authentication hardening:

- open and keep one verified SSH maintenance session active for the full hardening window
- if your VPS provider console is available, open a console session too and keep it ready
- do not begin lockout-risking changes unless at least one live admin shell is already open
- continue hardening only while access remains verifiable from fresh sessions
- if access uncertainty appears at any point, stop and recover access before further changes

### Private overlay first

- Put the VPS on a **private tailnet/VPN** (e.g. Tailscale, WireGuard) and **administer over that**, not over raw public SSH.
- If you must expose SSH at all, **restrict by source IP** or VPN-only; avoid `0.0.0.0/0` for SSH.

### SSH hardening (baseline)

- **Key-based auth only**; disable password authentication and **disable root SSH login**.
- **Separate keys**: operator login vs automation/deploy keys; different passphrases; never reuse a personal key across unrelated systems without reason.
- **Avoid SSH agent forwarding** unless you understand the risk (forwarded agent can be abused on the remote side).
- Enable **audit logging** and centralized or tamper-evident logs where feasible; review failed auth and sudo (if any) periodically.

### Firewall

- **Default deny inbound**; allow only required ports (often VPN overlay makes public SSH unnecessary).
- Explicit **egress allowlists** for hardened profiles (model APIs, package mirrors, integrations)—document exceptions; alert on drift.

### Runtime identity on the VPS

- **Provisioning:** root or sudo-capable user **only** for install, kernel updates, and break-glass.
- **Routine:** a **dedicated standard user** for the agent process, workspace, and service units—**no sudo** for that user.

### Chat and messaging as a control plane

Messaging platforms are **semi-trusted**: MFA on operator accounts, **bot token hygiene** (rotation on leak, minimal scopes), **immutable-ID allowlists** (not display names), no open DMs for owner-only actions. Treat inbound messages as **untrusted content** for instruction-following (see canonical security policy).

---

## Secrets and credentials (agent infrastructure)

**Where secrets should live**

- **Canonical store for the agent provider:** API keys, gateway tokens, and tool-related secrets belong under **`AGENT_HOME/.env`** (typically under the agent’s home directory on the machine where the agent runs, e.g. `~/.agent/.env`; with **profiles**, each profile has its own `AGENT_HOME`, so each gets its own `.env`). Setup and CLI flows write here; the file should remain **outside** git and **not** copied into public artifacts.
- **Workstation vs runtime:** On a **VPS runtime**, the same rule applies: secrets for the running gateway/agent live in that host’s **`AGENT_HOME/.env`** (owned by the **runtime user**), not in the application repo. Do **not** put your operator password vault or full production credential stores there—only **narrowly scoped** keys the agent needs.
- **Repository `.env`:** A project-root `.env` may exist for **local development** and is usually gitignored. Treat it as **non-authoritative** and avoid relying on it for production; prefer the agent home **`AGENT_HOME/.env`** (e.g. `~/.agent/.env` on the workstation or the same path on the runtime host) so secrets are not tied to a clone path.

**Posture**

- Long-lived keys in a **plaintext user-only file** (e.g. Unix `chmod` 600) is a common CLI baseline—it is **not** the same as a vault or HSM.
- **Recommendation — before production:** move toward **stronger authentication and storage** than flat files: **hardware security keys** (e.g. FIDO2) and provider flows that **avoid persisting long-lived secrets on disk** where available; **secrets managers** or **runtime injection** (cloud KMS, vault, env from orchestrator) for production; **rotate** keys on any suspected leak.

---

## What You Are Building

Before deploying any runtime policies or prompts, you should end up with:

- one workstation with a **standard daily user** (no sudo) and a **separate admin account** used only for bootstrap/maintenance—not for runtime
- one **dedicated VPS** (or optional guest VM) **only** for the agent/gateway runtime
- on the VPS: one **provisioning** identity (root/sudo) for setup/patching only
- on the VPS: one **runtime user** used only for the running agent and workspace (no sudo)
- one **runtime workspace** under `AGENT_HOME/workspace/` with:
  - `workspace/input`
  - `workspace/output`
  - `workspace/logs`
- one **canonical runtime policy root** under `AGENT_HOME/policies/` (full policy bundle **and** generated / routine edits such as `core/governance/generated/` — **not** under `workspace/`)
- one **dedicated browser profile** on the runtime host if a browser is used—only for the agent
- **no** mounting workstation directories into the runtime workspace
- **no** password manager or personal vault on the runtime host
- **no** personal/work browser login inside the runtime browser profile
- **no** public exposure of the gateway or browser control
- **no** production SSH targets or production credential stores on the runtime host beyond narrowly scoped secrets
- **API and tool secrets** for the agent held under **`AGENT_HOME/.env`** on the correct host (workstation or VPS), not committed to the repo—see **Secrets and credentials** above
- **Dedicated service identities** for each integration the agent will use (inference providers, Git/forges, messaging bots, optional tool APIs), **and** where applicable an **agent-only** identity for your **IDE / agent-assisted coding environment**—created **before** you run the policies pipeline or expect full automation—see **Step 9**

---

## Step 1 — Harden the Workstation First

The workstation is more sensitive than the runtime. Start there.

Do this:

- keep the OS fully patched
- use a strong login password / FileVault
- enable full-disk encryption
- keep the **password manager on the workstation only** (Standard user)
- keep **long-lived operator secrets** off the VPS except minimal scoped API keys the agent needs
- keep personal browser sessions on the workstation only
- keep sensitive files on the workstation only
- turn on the host firewall
- move toward deny-by-default inbound on the workstation
- do not expose public services from the workstation for this setup

Do not do this:

- do not use the **administrator** macOS account for daily runtime or messaging control
- do not run the **gateway/agent 24/7** on the workstation at highest posture
- do not let the runtime agent attach to your normal browser on the workstation
- do not sync your personal vault or production kubeconfigs onto the VPS “for convenience”

---

## Step 2 — Provision the Runtime VPS

Create or allocate a **dedicated VPS** only for this runtime.

Requirements:

- not shared with unrelated workloads
- treated as disposable/rebuildable
- initial access: prefer **cloud console** or **VPN**, then harden SSH as above
- document provider, region, and **backup/snapshot** strategy before going live

Immediately after the OS is installed:

- install security updates
- create the **runtime** standard user and lock down SSH as above
- take a **snapshot or image** of the clean base
- record the server purpose and **allowed network paths**
- do not log into personal cloud accounts on the VPS
- do not reuse personal workstation identity on the VPS

---

## Step 3 — Separate Provisioning vs Runtime Accounts (on the VPS)

Use two separate Linux accounts (or equivalent).

### Provisioning / maintenance (root or sudo-capable)

Use only for:

- initial OS configuration
- installing approved software and services
- patching
- systemd units that require elevated install
- emergency break-glass recovery

Rules:

- do not run the agent **as root** or as this user for routine operation
- do not browse casually under this identity
- do not use it for day-to-day chat-driven operations

### Runtime user

Use only for:

- running the AI agent / gateway under service supervision
- owning the runtime workspace
- owning the dedicated agent browser profile (if any)

Rules:

- must be a standard user
- must not have sudo capability **for routine operation**
- must not silently elevate

---

## Step 4 — Install Only the Minimum Necessary Software on the VPS

Use the provisioning account for installation.

Install only what you actually need, for example:

- runtime dependencies for the agent
- reverse proxy or VPN client if in architecture
- audit or logging tools you explicitly want

Do not install by default:

- password managers
- personal messaging apps (control plane is via your **workstation** chat clients → gateway on VPS)
- personal cloud-drive sync
- broad developer toolchains you will not use
- Docker socket exposed to the runtime user without hardening review

---

## Step 5 — Set Up the Runtime Workspace

Log in as the **runtime user** and create the workspace under `AGENT_HOME`.

Create:

- `workspace/input`
- `workspace/output`
- `workspace/logs`

Optionally create:

- `workspace/tmp`
- `workspace/cache`

Rules:

- all runtime file activity should stay inside this workspace
- logs should stay inside `workspace/logs`
- downloads should go into the workspace only
- no broad filesystem roots
- no mounted workstation paths
- canonical policy files and routine runtime-editable policy material (including generated markdown) live under `AGENT_HOME/policies/` (outside `workspace/`)

Make a note of the exact canonical path to this workspace.

---

## Step 6 — Create the Dedicated Agent Browser Profile (if applicable)

If the runtime uses a browser:

Create **one** browser profile only for the runtime agent.

Required properties:

- not logged into personal accounts
- not logged into work accounts
- no sync
- no password manager
- no imported browsing data
- no personal extensions
- downloads restricted to the workspace
- use incognito/ephemeral mode where compatible

Do not attach the agent to a personal browser on the workstation.

---

## Step 7 — Set the Network Posture

Default posture:

- **loopback-only bind** for the runtime/gateway services facing local consumers
- **no** public internet exposure of control surfaces
- **no** public SSH open to the world without VPN/IP restriction
- **no** public browser-control exposure
- remote admin access via **VPN/tailnet** and/or explicit tunnel to loopback
- deny-by-default firewall on the VPS

Do not make anything internet-accessible “just for testing.”

### Recommended checkpoint before deeper SSH/firewall hardening

Before disabling root SSH login or tightening firewall defaults, establish and verify private admin access over a tailnet/VPN (for example Tailscale):

1. Install and enroll the VPS in the tailnet.
2. Install and enroll the operator workstation (macOS) in the same tailnet.
3. Verify operator login to the VPS using tailnet addressing (Tailscale IP or MagicDNS) while the current public SSH path still works.
4. Record tailnet host/IP values in operator metadata (for example `SSH_TAILSCALE_IP`, `SSH_TAILSCALE_DNS`).
5. Pause for operator confirmation that private-path access is stable before any additional lockout-risking action.

Quick-start (Tailscale example):

- VPS (Ubuntu/Debian-class):
  - `curl -fsSL https://tailscale.com/install.sh | sh`
  - `systemctl enable --now tailscaled`
  - `tailscale up --ssh --hostname <runtime-hostname>`
- Workstation (macOS):
  - `tailscale up`
- Validation:
  - from macOS: `tailscale status`
  - from macOS: `tailscale ping <runtime-hostname>`
  - from macOS: `ssh <maintenance-user>@<runtime-hostname>`

Optional: configure runtime host as a controlled exit node

- On VPS runtime host:
  - enable forwarding first (persisted), for example:
    - `net.ipv4.ip_forward=1`
    - `net.ipv6.conf.all.forwarding=1`
  - `tailscale up --ssh --advertise-exit-node`
- In the Tailscale admin console:
  - approve the node’s advertised exit-node capability/routes
- On operator workstation (after approval):
  - verify node appears as an available exit node in `tailscale status`
  - verify with `tailscale exit-node list`
  - optionally enable it for the current session only when needed
  - confirm SSH/admin path remains healthy before and after enabling exit-node mode
- Keep this as an explicit checkpoint: do not continue to deeper hardening until the operator confirms exit-node approval state and connectivity behavior.

Operational note:

- If a prior node with the same hostname exists, Tailscale may assign a suffixed MagicDNS name (for example `runtime-host-1.<tailnet>`). Use `tailscale status --json` on the runtime host and record `Self.DNSName`/`Self.TailscaleIPs` as the canonical admin endpoint.
- To reclaim the unsuffixed hostname, remove stale/retired devices with the same hostname from the Tailscale admin console, then re-apply the runtime hostname (`tailscale set --hostname <runtime-hostname>` or `tailscale up --hostname <runtime-hostname> ...`) and verify the updated `Self.DNSName`.

Do not retire remaining public admin paths until these validation steps succeed in fresh sessions.

---

## Step 8 — Decide the Builder vs Runtime Split

Before deploying policies, choose who does what.

Recommended split:

### Cursor or equivalent coding agent (on the workstation)

Use as:

- builder
- file-level deployer
- editor

Prefer the **Standard** macOS user without sudo; use admin only when the OS requires it.

### Runtime agent (on the VPS)

Use as:

- activator
- validator
- operator against allowlisted tools
- policy-following executor
- preflight/audit runner

The builder lays the rails. The runtime operates on the rails **on the VPS**.

### Fork upstream and clone on the workstation

When the agent provider publishes source on a **Git forge** (e.g. GitHub-class hosting):

1. **Fork** the upstream repository into the **agent-owned** forge account (the same identity you use for narrowly scoped PATs/SSH keys in Step 9—not your unrelated personal user, when policy requires separation). That fork is where you branch, open pull requests, and attach CI as needed.
2. **Clone** the **fork** (not an anonymous download of upstream only) using your **IDE** or **agent-assisted coding environment**, authenticated as that same agent-scoped forge identity.
3. **Place the working copy** under the **macOS user account where you run the IDE** for daily builder work. In this runbook that is normally the **Standard** user (see **macOS account model** above)—**not** the **administrator** account, which is reserved for bootstrap and system maintenance. A clone that lives only under the administrator home directory is invisible to the Standard user’s sessions unless you duplicate it or use shared storage deliberately.

**Why:** the builder edits policies and code from the workstation; the runtime on the **VPS** may have its **own** clone or deploy artifact—those are separate paths. The workstation clone must be reachable from the account that actually opens the IDE.

---

## Step 9 — Provision isolated service accounts (before the policies pipeline)

After the **runtime environment** exists (workstation split, VPS, workspace, network posture) and **before** you rely on a fully wired agent or run the **policies verification pipeline** (`start_pipeline.py` — see [`policies/core/pipeline-runbook.md`](pipeline-runbook.md)), provision **dedicated identities** for everything the agent provider’s setup, wizard, or runtime will need. Goal: the agent uses **its own** accounts and narrowly scoped tokens—not your personal logins—for routine operation.

### Principle

- **One workload, one identity** where platforms allow it: separate from your day-to-day GitHub user, personal API keys, and personal messaging accounts when policy or risk warrants it.
- **Builder environment:** where you use an **IDE** or other **agent-assisted coding environment** (editor + embedded agent features), use a **dedicated login or profile** for that stack—agent-only—rather than your personal day-to-day identity when policy calls for isolation (see table row below).
- **Least privilege:** read-only or single-repo scopes for Git; minimal chat/API scopes for bots; only the inference providers you actually enable.
- **Secrets only in `AGENT_HOME/.env`** (or your deployment’s equivalent) on the correct host—never committed to the repository. See **Secrets and credentials** above.

### What to create (inventory and check off)

Use the agent provider’s documentation and setup prompts as your checklist. Typical categories:

| Area | What to provision | Isolation note |
|------|-------------------|----------------|
| **Inference / model APIs** | API keys or tokens for each enabled provider (aggregators, direct APIs, optional base URLs) | Separate from personal playground keys if you want a hard split; store only what the runtime needs |
| **Git / forge (GitHub, GitLab, …)** | PAT, fine-grained token, or deploy keys limited to repos the agent may access; optional machine user; **fork** upstream into the agent forge account then **clone** the fork on the workstation (see **Step 8 — Fork upstream and clone**) | Narrow repo/org scope; not your primary SSO identity if you can avoid it |
| **Messaging / gateway** | Bot tokens / app credentials (Telegram bot, Slack app, Discord application, etc.) | Bots are first-class identities; use allowlists and MFA on *your* operator account separately |
| **Search, web, browser automation** | API keys for search, crawling, or remote browser products if those tools are enabled | Dedicated key; rate-limit aware |
| **Cloud & infrastructure** | IAM user, service principal, or API role for any cloud CLIs/APIs the agent will call | Minimal policy; separate from prod admin |
| **Containers / registry** | Read/pull or push credentials only if workflows require them | Scoped registry |
| **MCP, plugins, skills hosts** | Any URLs, tokens, or OAuth clients required by optional integrations | Same rules: dedicated or scoped, not personal vault export |
| **IDE / agent-assisted coding environment** | A **separate** vendor or OS account (or dedicated profile) used only for the editor + embedded agent where the product supports it | Keeps agent chat history, extensions, and sync boundaries off your personal identity; align Git/terminal inside that environment with the same scoped tokens you use for the agent workload |

### IDE and agent-assisted coding environment (agent-only)

If your workflow uses an **IDE** or similar **agent-assisted coding environment** (interactive editor with built-in agent/chat features), provision credentials **used only for that role**:

- Prefer a **dedicated account** or **workspace profile** at the product/OS level when available, so cloud sync, identity, and defaults are not shared with your personal daily profile.
- Sign in to **inference or plugin features** inside that environment with keys or subscriptions scoped to **agent work**, not personal accounts, where you can separate them.
- Match **Git and terminal** identity inside that environment to the **same** narrow tokens and repos you provisioned for the agent (see **Git / forge** above)—avoid mixing personal SSH keys or org-wide access.
- This is **in addition to** the macOS Standard user vs admin split: the IDE/agent coding stack gets its own **logical** identity when you want the smallest blast radius for prompt-injected or tool-mediated actions during development.

### Process

1. **Inventory** every variable or account the setup flow asks for (including “optional” tool APIs you plan to enable soon), **and** whether you will use a dedicated **IDE / agent-assisted coding environment** identity (table row above).
2. **Create** accounts or tokens **before** you need the agent unattended: register bots, create PATs, enable provider billing if required; configure the **agent-only** IDE/coding-environment login or profile when you adopt that split.
3. **Record** values into **`AGENT_HOME/.env`** on the workstation and/or VPS as appropriate; use the **runtime user** on the VPS for runtime-only secrets.
4. **Document** outside the repo (operator runbook) which identity owns which integration, for rotation and incident response.
5. **Do not** run the policies pipeline expecting a green path until **mandatory** secrets for your chosen profile exist if the pipeline or validators depend on them (optional keys can wait).

### Operator accounts vs agent accounts

- **Your** accounts (e.g. messaging login you use to talk to the bot): protect with MFA; they are not the same as **bot tokens** stored on the server.
- **Agent/service** accounts: no human inbox required where bots suffice; prefer tokens that can be rotated without touching your personal SSO.
- **IDE / agent-assisted coding environment (agent-only):** distinct from both—used only for the editor + embedded agent workload when you adopt a separate profile; not a substitute for the **runtime VPS** identity, but part of the same overall isolation story on the workstation.

---

## Step 10 — Prepare the Deployment Entry Files

Before activation, place these entry files where the builder and runtime can access them. In runtime deployments, stage the policy bundle and runtime-editable subtrees under **`AGENT_HOME/policies/`** (see `start_pipeline.py` with `--policy-root`):

- `policies/core/security-first-setup.md`
- `policies/core/unified-deployment-and-security.md`
- `policies/core/deployment-handoff.md`
- `policies/core/runtime/agent/BOOTSTRAP.md`
- `policies/core/runtime/agent/AGENTS.md`

The order is intentional (see the “Required Order of Operations” section above).

Do not pre-create runtime-editable policy trees or `operations/` in workspace before the pipeline run. Those outputs should be materialized by `start_pipeline.py` during deployment handoff.

---

## Step 11 — Keep Integrations Off at First

Before first activation, keep these disabled unless absolutely needed:

- Slack
- Telegram
- Discord
- email
- calendar
- contacts
- notes
- cloud storage
- databases
- external API surfaces
- plugins/hooks/skills
- execution
- browser control beyond what is needed for validation

If you later enable integrations, use:

- immutable IDs
- owner-only approval actions
- read-only scopes where possible
- no config writes from chat by default
- no broad/open DM access by default
- no username/display-name trust where stable IDs exist

---

## Step 12 — Run Manual Human Validation Before Any Agent Activation

Before allowing any runtime agent to activate, manually verify:

### Workstation/runtime separation

- no shared folders from workstation mounted into runtime workspace (if using VM: clipboard/sharing off)
- runtime is on **VPS** (or isolated VM), not on macOS admin account

### Account separation

- macOS **admin** exists and is **not** used for routine runtime
- macOS **Standard** daily user exists without sudo
- VPS **runtime** user exists and is non-sudo for routine work
- provisioning identity on VPS not used for daily agent process

### Browser isolation (if browser on runtime)

- dedicated agent profile exists
- no login / no sync / no password manager
- downloads go to workspace

### Workspace

- workspace exists with input/output/logs
- no workstation mounts inside workspace
- `operations/` exists under `AGENT_HOME/workspace/memory/runtime/operations/`
- canonical runtime policy tree (including generated / editable subtrees) exists under `AGENT_HOME/policies/`

### Network posture

- gateway intended to bind loopback (or private interface per policy)
- no public exposure path for control plane
- SSH not world-open without compensating controls
- no full production vault on VPS

### Entry-file readiness

- deployment entry files exist (see Step 10)

### Isolated service accounts

- inference, Git, messaging, and tool API identities created per Step 9 (as applicable)
- **IDE / agent-assisted coding environment:** agent-only login or profile in use where you chose that split (Step 9)
- **Git / workstation:** upstream forked into the agent forge account; working tree cloned where the **IDE runs** (typically the **Standard** macOS user—Step 8), not only under the administrator account
- scopes reviewed; no personal-only credentials required for routine agent operation unless explicitly accepted

### Secrets (agent provider)

- inference and tool API material is under **`AGENT_HOME/.env`** on the host where the agent runs (not committed to the repo)
- production path does not rely on a repo-local `.env` as the sole store

If any of these fail, fix them before moving on.

---

## Step 12A — Reproducible hardened runtime blueprint (generic, provider-agnostic)

Use this as an implementation pattern for any agentic runtime on a VPS. This section is intentionally tool-agnostic and should be treated as the default secure baseline unless a stricter internal control applies.

### 1) Private admin plane first, then remove public admin exposure

- Establish a private management overlay (VPN/tailnet) for all operator administration.
- Verify admin access over private addressing before changing SSH listeners.
- Bind SSH daemon to private interface addresses only (no wildcard bind).
- Disable any service/socket activation path that re-binds SSH on all interfaces.
- Keep public SSH closed once private management is confirmed.

### 2) Strong SSH authentication and identity controls

- Enforce key-based SSH only.
- Disable root SSH login.
- Disable password and challenge-response SSH auth.
- Use distinct identities:
  - **maintenance identity** (sudo-capable, human-operated)
  - **runtime identity** (non-sudo, service identity)
- Avoid convenience bypasses (for example, passwordless sudo) in steady state.

### 3) Provisioning vs runtime separation (mandatory)

- Provision and patch as maintenance identity only.
- Run all long-lived agent services as a dedicated runtime user.
- Ensure runtime user is not in sudo-capable groups.
- If a service is discovered running as root, migrate it immediately to the runtime user and remove conflicting legacy service units.

### 4) Workspace boundary model

Create and enforce a dedicated runtime workspace under the runtime user, with at minimum:

- `workspace/input`
- `workspace/output`
- `workspace/logs`

Recommended:

- `workspace/tmp`
- `workspace/cache`

Rules:

- Runtime command working directory defaults to the workspace root.
- Runtime file operations are constrained to workspace paths by policy.
- Agent state/config directories are separated from task workspace directories.
- Operational registers and project archival memory live under `AGENT_HOME/workspace/memory/runtime/operations/`.
- Runtime policy consumption and routine editable/generated policy content both use **`AGENT_HOME/policies/`** (outside `workspace/`).

### 5) Host firewall posture (default-deny inbound and outbound)

- Set default deny inbound.
- Set default deny outbound for hardened profiles.
- Add explicit allow rules only for:
  - private overlay interface traffic
  - DNS
  - HTTPS (and HTTP only if operationally required)
  - time sync
  - overlay transport bootstrap and keepalive traffic
- Document every outbound exception with justification and owner.

### 6) Drift detection and auditability

- Snapshot approved firewall rules after change control.
- Run periodic drift checks and emit an auditable alert when current rules differ from approved baseline.
- Keep a small local hardening readme on-host describing intended network policy and exception process.

### 7) Runtime control surfaces

- Keep control APIs/gateways bound to loopback or private interface only.
- Do not expose control-plane services on public interfaces by default.
- Use a service manager (systemd/launchd equivalent), not ad-hoc detached shell backgrounding.

### 8) Agent role segmentation profile model (logical least privilege)

Use separate agent profiles/roles for major task classes:

- read-only inspection
- write (non-destructive edits)
- deletion/cleanup
- terminal execution
- research
- browser automation
- messaging dispatch
- scheduling/cron operations
- scripted pipeline/code execution
- memory/recall operations
- delegation/orchestration
- router/orchestrator

Profile rules:

- each profile has explicit scope and refusal rules
- each profile defaults to manual approval for dangerous execution
- no persistent dangerous allowlists by default
- each profile runs with the same non-sudo runtime OS identity
- router role must classify intent first, then assign least-privilege profile

### 9) Operator-in-the-loop execution policy

- For destructive, privileged, or ambiguous actions: require explicit operator approval before execution.
- If request intent is mixed, split into staged subtasks with separate approvals.
- If intent is unclear, pause and ask clarifying questions instead of guessing.

### 10) Practical validation checks before moving forward

Confirm all of the following:

- public SSH is closed and private admin path works
- root SSH login is denied
- runtime services are running as non-sudo runtime identity
- firewall defaults are deny/deny with explicit allowlists
- runtime API/gateway bindings are private-only
- workspace directories exist and are owned by runtime user
- profile segmentation exists and router policy is defined
- dangerous command flow remains manual approval by default

Only proceed to the next file after these checks pass.

---

### 11) Lockout-safe SSH and firewall change-control (mandatory)

When changing SSH listener ports, bind posture, authentication, or host firewall rules on a VPS:

1. Establish at least one verified out-of-band recovery path first (provider console/recovery ISO).
   - If console/recovery is unavailable or known broken, treat this as a hard blocker and do not proceed.
2. Snapshot current SSH and firewall state before modification.
3. Add the new SSH port/rule first (allowlist source if possible), then validate daemon config (`sshd -t`).
4. Restart SSH and verify a new login succeeds on the new path **before** removing the old one.
5. Keep old SSH access open until end-to-end verification is complete from a second session.
6. Remove old port/rules only after successful validation and logging.
7. Record the exact rollback commands and execute a post-change audit immediately.

Hard rules:

- Never change SSH port and close the old port in one unverified step.
- Never treat “add a new SSH access port” as “replace existing listener now.” Keep the current working port active until dual-path login is verified from fresh sessions.
- If the host uses systemd socket activation (`ssh.socket`), do not switch activation mode (`ssh.socket` ↔ `ssh.service`) during the same remote hardening step. Stabilize one mode first, then add the new port and verify both listeners before any mode migration.
- Never assume provider console/recovery is available. If access control is being changed, operate as if console recovery is unavailable and full rebuild is the only fallback.
- Never remove or weaken an existing verified access route until another independent route is proven in a fresh session.
- Never restart SSH after auth/bind/firewall edits without a pre-armed automatic rollback that restores a known-good config and listener.
- Never assume SSH key passphrase equals remote sudo password.
- Never assume passwordless sudo exists; treat privileged changes as interactive unless explicitly confirmed.
- If privileged access is unavailable, stop and use break-glass recovery (console/root path) rather than repeated failed remote attempts.
- Never set or rotate a maintenance-user sudo password without immediately handing that value to the human operator via an approved secret channel they control.
- Never disable root SSH login (or any break-glass remote path) until all of the following are proven in a fresh session:
  - maintenance user key login works on the target port(s),
  - interactive sudo works with an operator-known password,
  - out-of-band console/recovery access is confirmed functional.
- Never store newly generated privileged credentials only on-host (for example root-only files) without operator confirmation and external recovery copy.
- Never edit local credential metadata to claim privileged/password state that has not been verified end-to-end after reconnect.
- Never proceed with SSH/auth hardening when operator explicitly requires a pre-change halt checkpoint; stop and request explicit go-ahead before any action that could impact access.
- If provider console is non-functional, require two independent remote admin paths (for example old SSH path + new SSH path) verified by both operator and agent before any credential or root-login changes.

Failure-pattern reference (must be prevented):

- Generating an unknown sudo password, then removing fallback/root remote access before operator verification, can create full-management lockout even if SSH daemon remains reachable.
- Changing multiple auth surfaces at once (user credentials, SSH root policy, port behavior) without checkpointed validation creates compounding failure risk.

Real incident note (documented failure and correction):

- What went wrong:
  - An SSH authentication policy change (`AuthenticationMethods publickey,password`) was applied and `sshd` was restarted as part of the same live step.
  - Validation was done against active config state, but not with an isolated candidate file and rollback guard.
  - After restart, remote SSH on the management port (`40227`) was no longer listening (`connection refused`), requiring console recovery.
  - Several command paths used `sudo ... bash -s`/heredoc patterns that were not deterministic under interactive password prompts, causing intended file writes/checks to be unreliable.
- Why this is unsafe:
  - Restarting `sshd` after auth-surface edits without a rollback timer can hard-cut all remote admin paths.
  - Checking only post-restart behavior is too late if the daemon fails to bind or loads conflicting directives.
  - Assuming “console recovery exists” creates false confidence; on many operators this means total lockout and forced droplet rebuild.
- Required safer method (must use this instead):
  1. Prove two independent admin routes before change (for example tailnet SSH route A and separate public/VPN route B, each tested in fresh sessions).
  2. Write proposed SSH changes to a candidate file (or staged include), do **not** immediately replace the active known-good file.
  3. Validate candidate syntax/semantics first with explicit config test (`sshd -t` against the intended config set).
  4. Apply changes using deterministic non-interactive command forms (no stdin-fragile heredoc/sudo patterns for critical edits).
  5. Keep one verified remote admin session open and start a second fresh-session login test before committing.
  6. Arm an automatic rollback job (time-delayed restore + ssh restart) before any restart.
  7. Restart SSH, verify listener bind (`ss -tlnp`) and successful fresh login on both independent routes.
  8. Cancel rollback only after both checks pass and operator confirms access.
  9. Apply one auth change per checkpoint (no bundled root/auth/port/firewall changes in one step).

Timed rollback pattern that worked in practice:

- Arm a rollback before restart (for example restore known-good file and restart `sshd` after 180 seconds).
- Restart SSH once.
- Immediately validate:
  - listener is bound on expected management port (`ss -tlnp`)
  - route A login works in a fresh session
  - route B login works in a fresh session
- If all checks pass, cancel the rollback timer; otherwise let rollback execute and stop.

Safest implementation sequence observed in practice:

1. Confirm two independent admin routes in fresh sessions before any change.
2. Keep one route active while changing only one control surface at a time.
3. Pre-arm timed rollback before any `sshd` restart tied to auth/listener edits.
4. Verify listener bind immediately after restart (`ss -tlnp`) before any further actions.
5. Verify route A login and route B login again after restart.
6. Only then cancel rollback and proceed to the next checkpoint.
7. Do not remove public/admin exposure until private admin path remains stable across fresh-session retests.

SSH auth compatibility note (important):

- On Ubuntu/OpenSSH builds where direct `AuthenticationMethods publickey,password` is rejected, enforce password-required login with:
  - `AuthenticationMethods publickey,keyboard-interactive`
  - `KbdInteractiveAuthentication yes`
  - `UsePAM yes`
- This still requires both factors on every SSH path (key + password prompt), while remaining compatible with host policy defaults.
- Validate with both tests after restart:
  - key-only login must fail
  - key + password login must succeed

Strict key+password enforcement procedure (recommended standard):

1. Pre-check:
   - confirm at least one active maintenance shell is open
   - confirm one additional fresh-session login path is available (or provider console is open and ready)
2. Capture baseline:
   - save current `sshd -T` auth-related output
   - save current listener state (`ss -tlnp`)
3. Stage config:
   - write candidate auth policy to the managed include file
   - validate with `sshd -t` before restart
4. Arm rollback:
   - pre-arm timed rollback that restores known-good SSH config and restarts SSH after a short timeout
5. Restart and validate immediately:
   - verify listener is bound on expected port
   - test fresh login with key-only (must fail)
   - test fresh login with key+password (must succeed)
6. Commit only after proof:
   - cancel rollback timer only after both tests pass and operator confirms access
7. Stop on any uncertainty:
   - if validation is ambiguous or access degrades, stop and let rollback execute or recover before further edits

Operator verification commands (fresh-session checks):

```bash
# 1) key-only must fail
ssh -S none -o BatchMode=yes -o PreferredAuthentications=publickey -o PubkeyAuthentication=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no <maintenance-user>@<host>

# 2) key + password must succeed
ssh -S none -o PreferredAuthentications=publickey,keyboard-interactive,password -o KbdInteractiveAuthentication=yes <maintenance-user>@<host>
```

Proven lockout-safe sequence (what worked):

1. Confirm maintenance-user key login and interactive sudo on the current SSH path.
2. Add the new SSH listener/port while keeping the current working port active.
3. Verify login on both old and new ports from fresh sessions.
4. Promote the new port as primary in operator metadata/env only after dual-path verification.
5. Remove the old port listener only after operator confirms they can log in on the new port.
6. Re-test login on the new port immediately after old-port removal.
7. Pause for explicit operator confirmation before any additional lockout-risking step (for example disabling root SSH login or tightening firewall rules).

Observed implementation detail that prevented repeat lockout:

- Remove temporary/recovery SSH include files after recovery (`/etc/ssh/sshd_config.d/*.conf`) if they reintroduce legacy ports or weaker auth settings.
- Keep one canonical hardening include with explicit target posture (single approved port + explicit `AuthenticationMethods` requiring key+password), then validate with `sshd -t`, `sshd -T`, and fresh non-multiplexed login tests.
- Never treat reused control-socket sessions as proof of authentication policy; always run fresh-session checks (`-S none`, `ControlMaster=no`) before concluding auth posture is enforced.

---

## Step 13 — What Happens Next

Once this file is complete, move immediately to:

- `policies/core/unified-deployment-and-security.md`

Pre-handoff hard gate before opening unified deployment:

- Capture and confirm effective SSH auth output (`sshd -T`) includes explicit `authenticationmethods` requiring both factors.
- Run and document fresh non-multiplexed auth tests:
  - key-only fails
  - key+password succeeds
- Proceed only after those checks pass in the current host state.

After that runbook, use:

- `policies/core/deployment-handoff.md`

That file should:

- direct the builder to deploy against the current policy tree
- direct the runtime to activate from the deployed structure
- explicitly include `BOOTSTRAP.md` in the deployment process
- ensure the bootstrapping process updates or instigates all attached agent markdown files
- ensure the user has a clear handoff into the full operating system

**Policies pipeline (when ready):** after you understand the runbooks and handoff, run the verify/index pipeline as described in [`policies/core/pipeline-runbook.md`](pipeline-runbook.md). That step **refreshes** `policies/INDEX.md` and validates layout—it does not replace environment hardening (Steps 1–8), isolated service accounts (Step 9), or the rest of this runbook.

---

## Minimal First-Step Checklist

1. secure the workstation; keep vault and personal sessions there; use a **Standard** daily user without sudo
2. reserve **macOS admin** for bootstrap/maintenance only—**not** runtime
3. provision a **dedicated VPS** (or isolated guest VM) for runtime only
4. harden SSH, firewall, and VPN/tailnet access; smallest public attack surface
5. separate **provisioning** vs **runtime** Linux accounts on the VPS
6. install only minimum required software on the VPS
7. create the runtime workspace
8. create the dedicated agent browser profile if needed
9. ensure no password manager, no sync, no personal login on runtime
10. set private/loopback posture for services; no public gateway test endpoints
11. **fork** upstream into the agent forge account and **clone** the fork under the **Standard** macOS user (IDE)—see Step 8; provision **isolated service accounts** (inference APIs, Git/forges, messaging bots, tool APIs, cloud/MCP as needed), **and** an **agent-only** identity for your **IDE / agent-assisted coding environment** when using that split; load secrets into **`AGENT_HOME/.env`** — **before** expecting the policies pipeline or unattended runtime
12. place the deployment entry files
13. confirm **agent secrets** live under **`AGENT_HOME/.env`** (not in git); plan **hardware key / vault / injected secrets** before production
14. verify the environment manually (including Step 12)
15. move to `policies/core/unified-deployment-and-security.md`, then `policies/core/deployment-handoff.md`
16. when ready, run the pipeline per [`policies/core/pipeline-runbook.md`](pipeline-runbook.md) (after handoff context—not a substitute for runbooks)

---

## Final Standard

The correct order is:

**secure workstation and accounts → isolate runtime on VPS → split provisioning vs runtime users → create workspace → isolate browser → lock down network posture → provision isolated service accounts (Git, APIs, messaging, tools, IDE/agent coding environment) into `AGENT_HOME/.env` → place entry files → verify environment → deployment handoff → policies pipeline when ready → bootstrap agent pack → activate only after audit**

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/firewall-exceptions-workflow.md](firewall-exceptions-workflow.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
