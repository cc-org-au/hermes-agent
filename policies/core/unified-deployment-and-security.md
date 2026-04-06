<!-- policy-read-order-nav:top -->
> **Governance read order** — step 3 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/firewall-exceptions-workflow.md](firewall-exceptions-workflow.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

<!--
  Read order within core/ (flat runbooks): (1) security-first-setup.md — read first
  (2) this file — unified-deployment-and-security.md
  (3) deployment-handoff.md — handoff after both runbooks
  Former numeric prefix: 000 → this runbook (follows 0000 security-first file).
-->

# Unified deployment and security runbook

## Purpose

This runbook explains how to deploy the full AI-agent operating system and security model as one unified workflow.

Operational filesystem layout for registers, generated markdown, and per-project archival memory is defined in `policies/core/governance/artifacts-and-archival-memory.md` and indexed from `policies/README.md`.

It merges:
- the deployment and agent-spawn runbook
- the security operations runbook

It is written for the Human Operator and/or the root-level global deployment agent.

It is the practical runbook for applying the canonical deployment pack in the correct order.

---

## Core Rule

Apply the system in this order:

1. **Policy first**
2. **Structure second**
3. **Security gating third**
4. **Agents fourth**
5. **Tasks fifth**

Do **not** start by creating many agents and then trying to impose structure and security afterward.

---

## Canonical Control Order

Use the documents in this order of importance:

1. `CANONICAL_AGENTIC_COMPANY_AND_SECURITY_DEPLOYMENT_PACK.md`
2. generated org, registry, audit, and alert files
3. role-specific startup prompts derived from the canonical pack
4. project-specific briefs
5. task-specific instructions

The canonical pack is the constitution.  
Role prompts are operational derivatives.  
Task instructions are local execution directives.

---

# 1. Unified Deployment Sequence

## Phase 0 — Clone and bootstrap runtime repository (mandatory first gate)

Before loading policy packs, generating governance files, or spawning any agents:

1. Log in as the runtime non-admin user (not the admin account).
2. Clone the target agent repository into that user's home directory.
3. Pause for interactive GitHub authentication/authorization if prompted.
4. Complete baseline dependency and environment setup required by the repository (for example: Python runtime, package manager bootstrap, virtual environment, and project dependencies).
5. Run the agent's setup/bootstrap command so the runtime home (for example `.agent`) and workspace structure are created.
6. Confirm the runtime home and workspace directories exist and are writable by the runtime non-admin user.
7. Confirm the agent can start successfully (interactive CLI/session startup check).
8. Re-validate SSH authentication policy with fresh, non-multiplexed sessions:
   - key-only login attempt must fail
   - key+password login attempt must succeed
9. Only then continue to Phase 1.

### Hard rule
Do not proceed to governance/security rollout until clone, dependency bootstrap, runtime-home creation, and agent startup are confirmed on the runtime user account.
Do not proceed if SSH auth checks are based on reused control sockets; use fresh non-multiplexed sessions for validation.

---

## Phase 1 — Load the Canonical Pack

The root/global deployment agent must receive the full canonical pack first.

### Objective
Give the root agent a full understanding of:
- allowed hierarchy
- allowed roles
- hard rules
- soft constraints
- deployment order
- memory model
- escalation rules
- task-state rules
- lifecycle rules
- client deployment logic
- security baseline
- trust model
- startup preflight rules
- safe mode rules
- alert severity rules
- security pipeline rules

### Output expected from root agent
Before any subordinate agents are created, the root agent should produce:

- `ORG_REGISTRY.md`
- `ORG_CHART.md`
- `AGENT_LIFECYCLE_REGISTER.md`
- `TASK_STATE_STANDARD.md`
- `BOARD_REVIEW_REGISTER.md`
- `CHANNEL_ARCHITECTURE.md`
- `SECURITY_ALERT_REGISTER.md`
- `SECURITY_AUDIT_REPORT.md`
- `SECURITY_REMEDIATION_QUEUE.md`
- `INCIDENT_REGISTER.md`

These files create the structural and security backbone before execution begins.

---

## Phase 2 — Build Organisational and Security Scaffolding

Before spawning delivery agents, define:

- hierarchy
- role registry schema
- naming rules
- lifecycle states
- reporting-line rules
- permission boundaries
- task-state standard
- evidence standard
- summary format
- board review format
- security alert schema
- security severity definitions
- startup preflight schema
- audit schema
- incident schema
- remediation queue schema

### Why
This prevents ad hoc agent creation and keeps the system interpretable, auditable, and secure from the start.

---

## Phase 3 — Spin Up Foundation Governance Roles

Create these first:

1. Chief Orchestrator
2. Org Mapper / HR Controller
3. Chief Security Governor

### Why first
These are the three top control pillars:
- one coordinates work and strategy
- one governs structure, role registry, lifecycle, and org hygiene
- one governs security posture, trust boundaries, alerting, and safe mode

Do not create project workers before these exist.

---

## Phase 4 — Spin Up Security Foundation Roles

Create these next:

4. Startup Preflight Security Agent
5. Continuous Drift and Monitoring Agent
6. Filesystem and Execution Security Agent
7. Browser and Web Security Agent
8. Integration and Identity Security Agent
9. Prompt Injection and Memory Defense Agent
10. Outbound Exfiltration Guard Agent
11. Patch, Dependency, and Supply-Chain Security Agent
12. Incident Response Agent

### Why next
These roles establish the baseline security envelope before broader operational activity begins.

---

## Phase 5 — Run Startup Security Gating Before Broader Expansion

Before spinning up the broader operating hierarchy, run:

1. startup preflight
2. machine-readable security audit
3. warning/critical classification
4. safe-mode decision
5. startup refusal decision, if applicable

### Hard rule
If any fail condition exists, refuse startup.
If any safe-mode trigger exists, allow only safe mode.
If warnings only exist, continue with remediation queue.

---

## Phase 6 — Spin Up Initial Functional Directors

Create only the initial default directors:

13. Product Director
14. Engineering Director
15. Operations Director
16. IT / Security Director

### Why next
These roles define function-level standards and support Project Leads later.

They should not become workers or general-purpose do-everything agents.

---

## Phase 7 — Prepare Standards Before Projects

Before active project delivery begins, the leadership and security layers should define:

- naming conventions
- task-state rules
- evidence rules
- summary rules
- escalation thresholds
- archive rules
- lifecycle review cadence
- board review cadence
- channel planning structure
- security review cadence
- drift review cadence
- patch review cadence
- incident handling thresholds
- break-glass procedure
- warning and critical escalation routes

This creates consistency before project-specific execution begins.

---

## Phase 8 — Onboard Active Projects

For each actual active project:

1. create one Project Lead
2. register that Project Lead formally
3. attach the project brief, constraints, and success criteria
4. attach any project-specific security constraints
5. allow the Project Lead to determine whether Workers or Supervisors are required

### Hard rule
Every active project must have one Project Lead before any subordinate project agent is created.

---

## Phase 9 — Spawn Execution Agents On Demand

Within each project:

- create Workers / Specialists only when actual work requires them
- create Supervisors only when coordination complexity justifies them

Never create a full delivery org chart in advance.

---

## Phase 10 — Review, Monitor, and Prune

At regular intervals:

- Chief Orchestrator runs structured board reviews
- Org Mapper / HR reviews usefulness, duplication, and lifecycle state
- Chief Security Governor reviews security posture
- Continuous Monitoring reviews drift and anomalies
- idle, duplicated, weak-value, or out-of-scope agents are paused, merged, or terminated
- unresolved WARNINGs are reviewed
- CRITICAL findings trigger immediate response

The system must remain lean and secure over time, not just at setup.

---

# 2. Agent Spawn Procedure

Never create an agent by simply dumping a large role prompt into an empty shell.

Use the following procedure.

## Step 1 — Define the Role Before Creation

Before an agent exists, the spawning authority must define:

- agent name
- role title
- department
- supervisor
- project affiliation, if any
- mission
- scope
- non-scope / boundaries
- permissions
- success metrics
- lifecycle state = Proposed

If the role has security implications, also define:
- trust level
- sensitive surfaces it may touch
- approval gates required
- whether it may trigger WARNINGs or CRITICALs
- whether it may activate safe mode

This definition must be recorded in the appropriate registry before activation.

### Why
This ensures the role exists as a governed unit before it exists as an active actor.

---

## Step 2 — Register the Agent

The Org Mapper / HR Controller, or the root deployment authority, should formally register the proposed role in:

- `ORG_REGISTRY.md`
- `AGENT_LIFECYCLE_REGISTER.md`

If security-relevant, also record in:
- `SECURITY_REMEDIATION_QUEUE.md` if the role exists to remediate a control
- `SECURITY_ALERT_REGISTER.md` if the role is tied to active alert handling

Minimum registry entry:

- name
- role
- department
- supervisor
- project
- mission
- scope
- permissions
- measurable impact
- lifecycle status
- creation date
- review date

### Hard rule
No agent should become active before it is registered.

---

## Step 3 — Instantiate the Agent Shell

Create the agent with only its minimum identity and authority boundaries:

- role identity
- supervisor
- department
- project, if any
- mission
- scope
- permissions

At this stage, do **not** give it full company-wide context unless that is truly necessary.

### Goal
Keep initial context small, role-specific, and security-bounded.

---

## Step 4 — Deliver the Startup Prompt

Once the shell exists, give the agent its startup bundle.

Every startup bundle should contain five elements:

### A. Identity
Who the agent is.

### B. Scope
What the agent owns.

### C. Boundaries
What the agent does not own.

### D. Rules
How it must behave.

### E. Current Objective
What it is being activated to do right now.

Without the current objective, agents become abstract and under-directed.

---

## Step 5 — Deliver the First Actual Task

After the startup prompt, send the first real task or mission.

Do not overload the startup message with:
- full company constitution
- all future possible tasks
- all possible responsibilities
- massive historical context

Startup prompt first.  
Task second.

---

# 3. What Each Agent Should Receive on Creation

Each newly activated agent should receive only the amount of context it needs.

## Root / Global Deployment Agent
Receives:
- full canonical deployment pack

## Chief Orchestrator / Org Mapper / Chief Security Governor
Receive:
- full relevant sections of the canonical pack
- or a compressed derivative sufficient to do their role fully

## Functional Directors / Project Leads
Receive:
- their role section
- shared rules on memory, escalation, task state, evidence, and summaries
- shared security rules relevant to their scope
- current mission

## Security Agents
Receive:
- their security role definition
- the relevant security sections of the canonical pack
- the alert severity model
- the safe mode rules
- their current monitoring or enforcement objective

## Workers / Specialists
Receive only:
- their role identity
- their narrow scope
- their hard rules
- the summary format
- the escalation threshold
- the current task
- the success condition

### Hard rule
Do not repeatedly feed the entire canonical pack to every agent.

---

# 4. Agent Startup Bundle Template

Use this structure for every new agent.

**Hermes deployments:** If the new agent is a **separate runtime** (own `HERMES_HOME`, credentials, or messaging gateway), create a **Hermes named profile** (`hermes profile create <slug>` → `~/.hermes/profiles/<slug>/`). Slugs are single path segments; reflect hierarchy in the name (e.g. `director-ops`, `project-xyz-lead`). Record slug ↔ role in `workspace/operations/ORG_REGISTRY.md` / `AGENT_LIFECYCLE_REGISTER.md`. For roles that exist only as prompts or delegate work inside one profile, no extra profile is required. See `policies/core/deployment-handoff.md` (Hermes profiles section).

```text
You are [ROLE NAME].

Supervisor: [SUPERVISOR]
Department: [DEPARTMENT]
Project: [PROJECT OR NONE]

Mission:
[1–3 sentence mission]

You own:
- [responsibility]
- [responsibility]
- [responsibility]

You do not own:
- [boundary]
- [boundary]
- [boundary]

Hard rules:
- [rule]
- [rule]
- [rule]

Reporting format:
- objective
- current status
- evidence
- blocker
- next action
- requested decision, if any
- memory recommendation: keep active / archive / close

If this role is security-relevant, also include:
- severity handling rules
- safe mode conditions
- escalation path

Current objective:
[immediate task]

Success metric:
[what counts as good performance]
```

---

# 5. Recommended Unified Spawn Order

Apply this exact order unless there is a compelling reason not to.

## Stage 1 — Root setup
1. load `CANONICAL_AGENTIC_COMPANY_AND_SECURITY_DEPLOYMENT_PACK.md` into the root/global deployment agent
2. have it generate the structural and security files:
   - `ORG_REGISTRY.md`
   - `ORG_CHART.md`
   - `AGENT_LIFECYCLE_REGISTER.md`
   - `TASK_STATE_STANDARD.md`
   - `BOARD_REVIEW_REGISTER.md`
   - `CHANNEL_ARCHITECTURE.md`
   - `SECURITY_ALERT_REGISTER.md`
   - `SECURITY_AUDIT_REPORT.md`
   - `SECURITY_REMEDIATION_QUEUE.md`
   - `INCIDENT_REGISTER.md`

## Stage 2 — Foundational agent creation
3. create Chief Orchestrator
4. create Org Mapper / HR Controller
5. create Chief Security Governor
6. register all three formally

## Stage 3 — Security foundation
7. create Startup Preflight Security Agent
8. create Continuous Drift and Monitoring Agent
9. create Filesystem and Execution Security Agent
10. create Browser and Web Security Agent
11. create Integration and Identity Security Agent
12. create Prompt Injection and Memory Defense Agent
13. create Outbound Exfiltration Guard Agent
14. create Patch, Dependency, and Supply-Chain Security Agent
15. create Incident Response Agent
16. register all formally

## Stage 4 — Security gating
17. run startup preflight
18. run security audit
19. classify INFO / WARNING / CRITICAL
20. if FAIL, refuse startup
21. if SAFE_MODE, start only in safe mode
22. if WARNING only, continue with remediation queue

## Stage 5 — Initial functional leadership
23. create Product Director
24. create Engineering Director
25. create Operations Director
26. create IT / Security Director
27. register all formally

## Stage 6 — Project creation
28. for each active project, create one Project Lead
29. register the Project Lead
30. attach project-specific brief, constraints, success metrics, and security constraints

## Stage 7 — Controlled execution expansion
31. Project Lead requests Workers as needed
32. register each Worker before activation
33. give each Worker a scoped startup bundle
34. create Supervisors only if coordination pain justifies them

## Stage 8 — Ongoing governance and security hygiene
35. run periodic board reviews
36. run periodic org hygiene reviews
37. run periodic drift reviews
38. run patch/dependency reviews
39. pause, merge, reassign, or terminate unnecessary agents
40. remediate WARNINGs and respond immediately to CRITICALs

---

# 6. Unified Security Workflow

## Startup workflow
At each startup or restart:

1. run startup preflight
2. run machine-readable security audit
3. classify findings into INFO / WARNING / CRITICAL
4. if any fail condition exists, refuse startup
5. if safe-mode trigger exists, start only in safe mode
6. if warnings only, allow startup with remediation queue
7. record audit results and operator-visible summary

### Admin-plane and network change protocol (required)

Before applying SSH/firewall/network-admin changes on a runtime VPS:

1. Confirm a tested recovery path (provider console or recovery mode).
2. Confirm privileged execution path (interactive sudo or root path) is available.
3. Apply additive access changes first (new port/rule), validate (`sshd -t`, live login), then remove legacy rules.
4. Require two-session verification before closing old admin access.
5. Run post-change audit and drift check immediately.
6. Require explicit `AuthenticationMethods` in final SSH policy so key-only fallback cannot silently remain active.
7. Validate auth outcomes with fresh non-multiplexed SSH sessions (no control-socket reuse).

If these conditions are not met, treat the change as high-risk and defer until break-glass prerequisites are satisfied.

### Runtime and messaging stabilization notes (required)

Apply these operational notes during first-time deployment and subsequent hardening:

1. **Bootstrap gate must be explicit**
   - Complete repository clone, dependency bootstrap, and runtime-home initialization as the non-admin runtime user before governance rollout.
   - Verify the runtime can start once interactively before introducing background services.

2. **Authentication checks must be revalidated with fresh sessions**
   - Validate final SSH policy using fresh, non-multiplexed sessions only.
   - Confirm key-only access fails where policy requires multi-factor login, and confirm the intended multi-step authentication succeeds.

3. **Run long-lived gateway processes as detached services**
   - Avoid keeping production gateway lifecycle tied to an operator shell.
   - Use a detached launcher or service manager so operator disconnects do not terminate messaging runtime.
   - Keep a single active gateway instance to avoid duplicate delivery behavior.

4. **Treat messaging onboarding as protocol-specific**
   - Validate channel/chat identifiers in canonical format for each platform before declaring setup complete.
   - Distinguish features that differ by chat type (for example, DM vs forum/thread-capable spaces).
   - Confirm allowlists with normalized identity formats before enabling broad traffic.

#### Hermes + Slack (Socket Mode) — verified production recipe

This is the checklist that restored a working Slack path when the gateway showed **Slack Socket Mode connected** and **Bolt running**, but **no** inbound traffic reached Hermes (no agent activity, no `Unauthorized user` lines, and with diagnostics enabled no `[Slack] bolt envelope` lines).

1. **Event Subscriptions → Subscribe to bot events** (at [api.slack.com](https://api.slack.com/apps), *Features → Event Subscriptions*). Include at minimum: `message.im`, `message.channels`, `message.groups`, `message.mpim`, and `app_mention`. Save the page after edits.
2. **Bot token scopes** — Ensure `channels:history` and `groups:history` are present (without them, channel messages often never reach the app). Align the rest of the bot scopes with the Hermes-recommended manifest (see repository `hermes_cli/slack_admin.py`, function `hermes_slack_manifest_dict`, or CLI helpers for manifest validate/export).
3. **App Home → Messages tab** — Turn on the **Messages** tab for the app so members can DM the bot (Slack blocks DMs otherwise even when scopes look correct).
4. **Reinstall the app to the workspace** after changing scopes or bot events so the installation picks up the new grants.
5. **`SLACK_ALLOWED_USERS`** — Use the Slack **Member ID** (`U…` from *Profile → … → Copy member ID*), comma-separated if needed. The Hermes gateway validates each listed ID with `users.info` on connect; a bad ID logs an explicit error once delivery is working.
6. **Socket Mode connection fan-out** — Slack may deliver Events API payloads over **any** of several concurrent WebSocket connections for the same app. Avoid running a second `hermes gateway` (or any other Socket Mode client) for the **same** Slack app and **same** app-level token elsewhere; otherwise some messages may be delivered to a non-production consumer. Prefer one production gateway per app, or separate app-level tokens per environment if Slack is used from multiple hosts.
7. **Narrowing “no events” vs “events but no reply”** — Set `SLACK_LOG_INBOUND=1` in `~/.hermes/.env` temporarily. Hermes then logs `[Slack] bolt envelope event type=…` for each event Slack hands to Bolt **before** listeners run. If that line never appears after a test DM or channel `@mention`, the fault is still Slack configuration or another consumer — not Hermes message routing. Remove or unset `SLACK_LOG_INBOUND` after debugging.

#### Slash commands (`/hermes-*`) and Slack `invalid_command_response`

**Symptom:** Slash commands such as `/hermes-reset` fail in Slack with **`invalid_command_response`** (Socket Mode slash acknowledgement validation) even though the app manifest lists `/hermes` and `/hermes-*`, and the gateway listener calls **`await ack()`** with an empty body (the correct **envelope-only** acknowledgement for Socket Mode; see Slack’s “Acknowledge events” documentation for slash commands over Socket Mode).

**Cause:** In **slack-bolt** (Python), with **`process_before_response=False`** (the **`AsyncApp`** default), **`AsyncioListenerRunner.run`** can return the **middleware** **`BoltResponse`** whenever that object is already non-`None`, **after** the listener has called **`ack()`**. The acknowledgement Slack should see is stored on **`request.context.ack.response`**, but that value was not always selected as the final response sent back over the Socket Mode client. The wrong body can produce a **`payload`** Slack rejects for slash commands.

**Fix in this repository:** `gateway/platforms/slack.py` calls **`_ensure_slack_bolt_slash_socket_ack_fix()`** when the Slack adapter connects. It wraps **`AsyncioListenerRunner.run`** once (process-wide): for payloads that look like slash commands (**`"command"`** present in the body), if **`ack.response`** is set, that response is used instead of Bolt’s returned value. The Hermes slash router still uses **`await ack()`** with no arguments and defers **`_handle_slash_command`** via **`asyncio.create_task`** so the ack stays immediate and user-visible replies use the normal messaging path. Regression tests: **`tests/gateway/test_slack.py`** (**`TestSlashCommandSocketAckFixOut`**).

**After upgrading this code:** Restart the gateway process that holds the Slack app token so the adapter loads the patch (see **Step 15 — VPS gateway operator account** below).

**Slack home channel (cron / proactive delivery):** In `~/.hermes/.env`, set `SLACK_HOME_CHANNEL` to the Slack channel ID used as the default delivery target (for a 1:1 DM with the bot this is a `D…` id). Obtain it by opening the DM from the bot side (`conversations.open` with the operator’s member id) or by sending `/sethome` from that DM after messaging works. Optional: `SLACK_HOME_CHANNEL_NAME` for display (for example `Slack DM`).

8. **Use structured health checks and automatic recovery**
   - Monitor gateway process state and per-platform connection state continuously.
   - On detected failure, restart the gateway once, then re-check platform connectivity.
   - If restart does not recover service, run automated diagnostics/fix routines and retry startup.
   - Record every failure/recovery cycle to a local watchdog log for auditability.

#### Watchdog daemon control pattern (recommended)

Implement a persistent watchdog service with this minimum behavior:

1. Run as a boot-started daemon under the runtime user context.
2. Check runtime status on a fixed interval (for example, every 30-60 seconds) using machine-readable state.
3. Mark unhealthy when either:
   - gateway process state is not `running`, or
   - any enabled messaging platform state is not `connected`.
4. Recovery ladder:
   - first attempt: restart gateway and re-check
   - second attempt: run automated diagnostics/fix (`doctor --fix` equivalent), then restart and re-check
   - final state: if still unhealthy, keep daemon alive, log hard failure, and continue periodic retries
5. Write append-only watchdog logs with UTC timestamps for each detection, action, and outcome.
6. Avoid spawning duplicate gateway instances; always restart via replace/stop+start semantics.

#### Watchdog hardening profile (recommended defaults)

When deploying the watchdog, include anti-thrash controls so transient upstream issues do not cause restart storms:

- **Base check interval:** 60s
- **Exponential backoff:** increase recovery delay after repeated failures (for example 60s -> 120s -> 240s), with a capped maximum
- **Max backoff cap:** 10 minutes
- **Jitter:** add random delay (for example 0-20s) to avoid synchronized restart waves across hosts
- **Recovery-attempt window:** track attempts in a rolling window (for example 4 attempts per 30 minutes)
- **Cooldown lockout:** when the attempt cap is exceeded, pause active recovery attempts for a cooldown period (for example 15 minutes), then resume checks
- **Reset policy:** on healthy state restoration, clear failure counters/backoff state immediately

#### Watchdog audit requirements

The watchdog log should include at least:

1. health-check failures with reason (gateway state and disconnected platforms)
2. each restart attempt and post-restart result
3. each diagnostics/fix invocation and completion
4. backoff/cooldown decisions with computed wait durations
5. recovery confirmation events

**Hermes Agent (messaging gateway):** Mandated health semantics (`watchdog-check`, live `gateway.pid`, recovery ladder, logging) are specified in [`gateway-watchdog.md`](gateway-watchdog.md). Governance read order places that file after [`deployment-handoff.md`](deployment-handoff.md).

9. **Run package operations from the correct working directory**
   - Perform dependency audit/fix commands from the project root where lockfiles exist.
   - If audit tools fail due to missing lockfiles or context mismatch, correct directory state first, then rerun.

10. **Confirm model endpoint and auth compatibility early**
   - Ensure configured model identifier, provider mode, endpoint format, and API key type are mutually compatible.
   - If authentication fails, switch to the provider’s supported endpoint/auth pattern for the selected model family.

11. **Prevent stale runtime mode/config drift**
   - After any configuration change affecting messaging mode, force a clean restart of all related runtime processes.
   - Verify live process arguments/runtime status match desired configuration, not just file contents.

## Continuous security pipelines

### Preflight pipeline
Cadence:
- every startup
- every restart
- before enabling integrations, plugins, browser control, or execution

### Drift pipeline
Cadence:
- on config change
- on integration change
- on plugin/hook/skill change
- every scheduled review cycle
- after network or browser-profile changes
- immediately after SSH/firewall policy changes

### Content-risk pipeline
Cadence:
- every inbound untrusted content item
- every file/document/archive intake
- every external message intake

### Outbound-control pipeline
Cadence:
- before every outbound send
- before every upload
- before every API call/webhook/message
- before every git push/share action

### Patch pipeline
Cadence:
- scheduled weekly review
- before every update
- immediately on relevant advisory publication

### Incident pipeline
Cadence:
- on every CRITICAL event
- on operator request
- on suspected compromise
- on perfect-storm state

---

# 7. Alert Handling

## INFO
- log only
- include in next routine summary

## WARNING
- open remediation item
- assign owner
- set due date
- include in operator summary
- recheck on next drift cycle
- promote to CRITICAL if repeated or combined with related failures

## CRITICAL
- trigger or recommend safe mode immediately
- open incident record
- notify operator immediately
- stop or deny risky operations until remediated
- require explicit operator review before returning to normal mode

---

# 8. Minimum Operator Review Cadence

## Daily
- review CRITICAL and WARNING queue
- review unresolved allowlist misses
- review blocked outbound attempts if any
- review safe mode status if active

## Weekly
- review patch/dependency posture
- review integration scopes and token hygiene
- review plugin/hook/skill inventory
- review stale warnings and drift trends
- review agent sprawl and dormant roles

## Before major change
- snapshot or image the **runtime VPS** (or guest VM if used)
- run preflight and audit
- review blast radius
- prepare rollback plan
- review break-glass necessity if applicable

---

# 9. Safe Mode Operations

When safe mode is active:
- no outbound sends
- no browser control
- no execution
- no memory writes
- no plugin/hook/skill activity except minimum runtime necessities
- operate only in text-only or read-only analysis mode
- no normal-mode restoration until remediation is validated by audit

---

# 10. Break-Glass Workflow

Use break-glass only for recovery, not convenience.

Procedure:
1. operator requests break-glass explicitly
2. security agent presents concise risk summary
3. exact scope, change, path, surface, or bind is stated
4. operator confirms after reading the summary
5. change is logged with owner, start time, and expiry
6. post-change audit runs immediately
7. rollback or expiry returns the system to baseline

Never use break-glass to allow:
- public internet exposure
- production SSH
- password manager connection
- host filesystem access
- privileged Docker
- permanent weakening of the baseline

---

# 11. Example: Spinning Up a Security Agent

## Example — Startup Preflight Security Agent

### Step 1 — Define
- role: Startup Preflight Security Agent
- supervisor: Chief Security Governor
- department: Security
- project: None
- mission: determine whether the environment may start normally, must start in safe mode, or must refuse startup
- scope: preflight validation only
- non-scope: incident remediation, patch review, company strategy
- permissions: read-only access to the state required for preflight
- success metrics: accurate PASS / WARN / SAFE_MODE / FAIL decisions with clear remediation steps

### Step 2 — Register
Add entry to org registry and lifecycle register.

### Step 3 — Instantiate shell
Create the agent with identity and scope only.

### Step 4 — Startup bundle
Provide:
- identity
- scope
- boundaries
- rules
- severity model
- safe mode conditions
- reporting format
- current objective

### Step 5 — First task
Example current objective:
- run the startup preflight checks for workstation/runtime separation, privilege level, bind posture, workspace containment, browser isolation, integration allowlists, and plugin/hook/skill state, then return PASS / WARN / SAFE_MODE / FAIL with remediation steps.

---

# 12. Example: Spinning Up a Project Lead

## Step 1 — Define
- role: Project Lead
- supervisor: Chief Orchestrator
- department: Project Delivery
- project: [Project Name]
- mission: deliver one isolated project using lean delegation and evidence-based tracking
- scope: project milestones, dependencies, blockers, worker coordination
- non-scope: company-wide policy, cross-company org governance
- permissions: project-local coordination
- success metrics: reliable delivery, clean status tracking, low context overhead

## Step 2 — Register
Add the Project Lead to org registry and lifecycle register.

## Step 3 — Instantiate shell
Create the Project Lead agent with only the project-relevant scope.

## Step 4 — Startup bundle
Provide its identity, rules, reporting format, project scope, and relevant security constraints.

## Step 5 — First task
Example current objective:
- translate the project brief into workstreams, define required subordinate roles, and produce an initial delivery plan with milestones, blockers, evidence requirements, and any project-specific security constraints.

---

# 13. What Not to Do

Do not:
- spin up all possible roles at once
- feed the full canonical pack to every agent
- let workers report raw logs upward
- let Project Leads exist without project isolation
- let directors become pseudo-workers
- let HR absorb project detail
- create supervisors before actual coordination pain exists
- create departments because they make the org chart look complete
- create agents without registry entries
- give agents broad vague mandates without immediate objectives
- enable integrations before immutable-ID allowlists exist
- allow browser control before browser isolation is validated
- ignore WARNINGs until they become CRITICAL
- continue in normal mode when safe mode should be active

These are the most common failure patterns.

---

# 14. Context Allocation Rules

Use context sparingly and by level.

## Root deployment agent
Gets the full canonical pack.

## Chief Orchestrator / Org Mapper / Chief Security Governor
Get deep role context and the key relevant sections of the pack.

## Directors / Project Leads
Get:
- role-specific operating instructions
- shared governance rules
- relevant security rules
- current mission

## Security Agents
Get:
- their role-specific security instructions
- alert and safe-mode logic
- current enforcement or monitoring objective

## Workers / Specialists
Get:
- minimal role bundle
- immediate task
- success condition
- escalation boundaries

### Principle
The lower the level, the less broad company context it should carry unless necessary.

---

# 15. Suggested First Live Deployment

If deploying today, use this exact sequence.

## Step 1
As the runtime non-admin user, clone the target repository into the user home path, complete dependency/environment bootstrap, run agent setup to initialize runtime-home/workspace paths, and verify the agent starts successfully.

## Step 2
Load the canonical deployment pack into the root/global deployment agent.

## Step 3
Instruct it to generate:
- `ORG_REGISTRY.md`
- `ORG_CHART.md`
- `AGENT_LIFECYCLE_REGISTER.md`
- `TASK_STATE_STANDARD.md`
- `BOARD_REVIEW_REGISTER.md`
- `CHANNEL_ARCHITECTURE.md`
- `SECURITY_ALERT_REGISTER.md`
- `SECURITY_AUDIT_REPORT.md`
- `SECURITY_REMEDIATION_QUEUE.md`
- `INCIDENT_REGISTER.md`

## Step 4
Create:
- Chief Orchestrator
- Org Mapper / HR Controller
- Chief Security Governor

## Step 5
Give each of those agents its scoped startup bundle.

## Step 6
Create:
- Startup Preflight Security Agent
- Continuous Drift and Monitoring Agent
- Filesystem and Execution Security Agent
- Browser and Web Security Agent
- Integration and Identity Security Agent
- Prompt Injection and Memory Defense Agent
- Outbound Exfiltration Guard Agent
- Patch, Dependency, and Supply-Chain Security Agent
- Incident Response Agent

## Step 7
Register all those security roles formally.

## Step 8
Run:
- startup preflight
- security audit
- warning/critical classification
- safe mode decision

## Step 9
If the environment passes or is warning-only, create:
- Product Director
- Engineering Director
- Operations Director
- IT / Security Director

## Step 10
Have the leadership and security layers define:
- naming rules
- task-state rules
- evidence rules
- reporting cadence
- archive rules
- review cadence
- warning/critical escalation flow
- break-glass procedure

## Step 11
When a real project appears:
- create one Project Lead
- attach project brief, success metrics, constraints, boundaries, and security constraints
- let the Project Lead determine whether subordinate roles are needed

## Step 12
Spawn Workers only when required.

## Step 13
Add Supervisors only after real coordination pressure exists.

## Step 14
Run periodic pruning and periodic security reviews so the system does not bloat or drift.

---

## Step 15 — VPS path only: `<cli> … droplet` on the workstation

**When to apply:** You use a **remote VPS runtime** and want the **same** operator CLI on the server, with **no** extra SSH arguments, paths, or env vars on each invocation.

**When to skip:** Local-only setups — use the CLI normally (no trailing `droplet`).

**Meaning of “agent” here:** the **operator CLI name** — the short command you run in a terminal (this repository’s default is `hermes`). There is **no** separate `agent-droplet` / `hermes-droplet` user command: you always run the normal CLI and append **`droplet`**. The pattern is always:

```text
<cli> <normal subcommands and flags …> droplet
```

The literal word **`droplet` must be the final argument** (after all flags). **Every** subcommand tree works the same way as locally — only the execution host changes. Examples for this product:

```text
hermes tui droplet
hermes doctor --fix droplet
hermes gateway watchdog-check droplet
hermes setup droplet
```

**Workstation prerequisites:** Encrypted private key, port, host, and **`SSH_USER`** (often an admin account) in the same env file **`ssh_droplet.sh`** reads. **`hermes … droplet`** sets **`HERMES_DROPLET_WORKSTATION_CLI=1`**, which ignores env-file **`SSH_PASSPHRASE`** / **`HERMES_DROPLET_ALLOW_ENV_PASSPHRASE`** so the **SSH key passphrase is typed interactively**. The remote CLI runs as **`hermesuser`** via **`sudo -u hermesuser`**: if **`SSH_SUDO_PASSWORD`** is set in that env file, **`ssh_droplet.sh`** uses **`sudo -S`** on the server; otherwise interactive **sudo** on the remote TTY. **`HERMES_HOME`** on the VPS defaults to **`/home/hermesuser/.hermes/profiles/<name>`** where **`<name>`** matches the workstation’s **`~/.hermes/active_profile`** (so your orchestrator or other sticky profile is used remotely); if sticky is **`default`** or missing, **`chief-orchestrator`** is used. The trailing word **`droplet`** is **not** a profile name — it only selects the SSH path. Hermes runs from **`/home/hermesuser/hermes-agent/venv/bin/python`**. **One-time on the VPS:** **`sudo bash scripts/core/droplet_bootstrap_hermesuser.sh`** (from a repo checkout) seeds **`chief-orchestrator`**; create additional profiles on the VPS if your workstation sticky name differs. For automation-only SSH, call **`scripts/core/ssh_droplet.sh`** without **`HERMES_DROPLET_WORKSTATION_CLI`**. **`scripts/core/ssh_droplet_user.sh`** uses interactive **`sudo`** to open a shell as **`hermesuser`**. **`agent-droplet`** sets **`HERMES_DROPLET_INTERACTIVE=1`** so the TTY gate passes under IDEs.

**Exact setup (this repository):** `.envrc` runs **`use flake`**, then records the real CLI path, then prepends **`scripts/core/`** to `PATH` so the shipped **`scripts/core/hermes`** shim runs first:

```bash
use flake
export HERMES_REAL_BIN="$(command -v hermes)"
PATH_add scripts/core
```

Run **`direnv allow`** once in the clone. Do **not** reorder those lines: `HERMES_REAL_BIN` must be captured **before** `PATH_add scripts/core`.

**Without direnv:** export **`HERMES_REAL_BIN`** to the absolute path of your real `hermes` (or other CLI) binary, then **`export PATH="/path/to/this/clone/scripts/core:$PATH"`** so the same shim name (`hermes` in this repo) shadows the real binary.

**Pip / venv entry point:** If you invoke **`hermes`** as **`venv/bin/hermes`** or **`python -m hermes_cli.main`** from an **editable** install of this checkout, **`hermes … droplet`** still works: **`hermes_cli.main`** detects a trailing **`droplet`**, applies local **`-p` / sticky** to the workstation, then **`exec`s `scripts/core/agent-droplet`**. You do not need **`scripts/core/`** ahead of **`venv/bin`** on `PATH` for that hop. **`droplet`** is a reserved CLI token, not a profile name — do not use **`hermes -p droplet`**.

### Step 15 — Workstation playbook (what worked, pitfalls, fixes)

**Venv (local vs VPS)**  
- **Workstation:** Use the checkout **`venv`** (`./venv/bin/python -m hermes_cli.main …`) or **`scripts/core/hermes`** (it calls that Python). Avoid a global `hermes` on `PATH` ahead of the repo unless you have pulled in the **`hermes_cli.main`** trailing-**`droplet`** behavior.  
- **VPS:** **`scripts/core/agent-droplet`** always runs **`cd /home/hermesuser/hermes-agent && ./venv/bin/python -m hermes_cli.main -p <profile>`** — the server must have that **`venv`** (bootstrap scripts create it).

**Remote venv (repeatable — SSH + one-shot commands as `hermesuser`)**  
- **`scripts/core/droplet_remote_venv.sh`** is sourced by **`ssh_droplet.sh`**, **`ssh_droplet_user.sh`**, and **`ssh_droplet_hermesuser_direct.sh`**. It prepends a remote shell snippet: **`cd`** to **`HERMES_DROPLET_REPO`** (default **`/home/hermesuser/hermes-agent`**), then **`source venv/bin/activate`** when **`venv/bin/activate`** exists.  
- **When it applies:** Remote commands run **as `hermesuser`** (or whatever **`HERMES_DROPLET_VENV_USER`** is set to — default **`hermesuser`**). That includes **`ssh_droplet.sh --sudo-user hermesuser '…'`** (used by **`hermes … droplet`** and by **`droplet_run.sh --droplet-require-sudo --sudo-user hermesuser`**), interactive **`ssh_droplet_user.sh`** / **`droplet()`** from **`scripts/shell/hermes-env.sh`**, and **`droplet_direct()`** when the SSH login user matches **`HERMES_DROPLET_VENV_USER`**.  
- **Configure (workstation `~/.env/.env`, optional):** **`HERMES_DROPLET_REPO`** if the clone path on the VPS is not the default; **`HERMES_DROPLET_VENV_USER`** if the runtime UNIX user differs.  
- **When it does *not* apply:** **`droplet_run.sh`** without **`--sudo-user hermesuser`** runs as **`SSH_USER`** (often admin) — no automatic venv prefix (you may still **`cd …/hermes-agent && ./venv/bin/python …`** explicitly in the remote string).  
- **Re-implement elsewhere:** Copy the snippet from **`droplet_remote_venv.sh`** or source that file from any new droplet SSH wrapper; keep **`ssh_droplet.sh`** as the canonical place that combines **`sudo`**, TTY reattach, and venv wrapping.

**PATH / “alias” (no separate `droplet` command)**  
- **`droplet` is only valid as the last argument:** `hermes`, `hermes doctor`, `hermes tui`, etc., then **`droplet`**. There is no supported `droplet` prefix command on `PATH`.  
- **Without direnv:** In **`~/.zshrc`**, prepend **`$HOME/hermes-agent/scripts/core`** then **`$HOME/hermes-agent/venv/bin`** when those paths exist, so **`hermes`** resolves to **`scripts/core/hermes`** from any directory.  
- **With direnv:** **`PATH_add scripts/core`** in **`.envrc`** is enough while **`cd`**’d into the clone; capture **`HERMES_REAL_BIN`** *before* **`PATH_add`** (see snippet above).

**Env files**  
- **SSH + droplet:** **`~/.env/.env`** (same path **`scripts/core/ssh_droplet.sh`** reads) holds **`SSH_PORT`**, **`SSH_USER`**, **`SSH_TAILSCALE_IP`** (or **`SSH_IP`**), optional **`SSH_SUDO_PASSWORD`** for non-interactive **`sudo -S`** to **`hermesuser`**, optional **`HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1`** plus **`SSH_PASSPHRASE`** for headless key unlock. Private key default: **`~/.env/.ssh_key`**.  
- **Hermes profile:** Sync the same SSH variables into the **active profile’s** **`$HERMES_HOME/.env`** if you use **`TERMINAL_ENV=ssh`** so in-app terminal and droplet agree on host/port/key. Use **`chmod 600`** on these files.  
- **Chief-orchestrator (VPS):** With **`hermes -p chief-orchestrator`**, **`HERMES_HOME`** is **`~/.hermes/profiles/chief-orchestrator`**. **`load_hermes_dotenv`** reads **`$HERMES_HOME/.env`** for that process — not the default **`~/.hermes/.env`** unless you copy or symlink. **`hermes profile show chief-orchestrator`** should report **`.env: exists`**. The repository provides **`scripts/core/ensure_chief_orchestrator_profile_env.sh`**: idempotent; seeds the profile **`.env`** from **`~/.hermes/.env`** or **`~/hermes-agent/.env`** if the profile file is missing. **`scripts/core/droplet_bootstrap_chief_orchestrator.sh`** runs it after **`profile use`**. Run the ensure script **as `hermesuser`** (or set **`HERMES_PROFILE_DIR`** / **`HERMES_AGENT_REPO`** explicitly). **`scripts/core/droplet_run.sh`** uses **`SSH_USER`** (often **`hermesadmin`**): its **`$HOME`** is wrong for **`~/.hermes/profiles/chief-orchestrator`**, so do not rely on **`droplet_run.sh`** alone to fix **`hermesuser`** profile secrets — use **`ssh_droplet.sh --sudo-user hermesuser '…'`** for profile-scoped maintenance.

**Sticky profile mistakes**  
- **`~/.hermes/active_profile` must not contain the word `droplet`.** That string is the **VPS hop suffix**, not a profile directory. If it was set to **`droplet`**, Hermes used to error or confuse profile resolution; current CLI **clears** that sticky and warns. Use a real profile name (e.g. **`chief-orchestrator`**) so the VPS **`agent-droplet`** **`-p`** matches.

**Failures we saw and how they were fixed**  
| Symptom | Cause | Fix |  
|--------|--------|-----|  
| `Error: Profile 'droplet' does not exist` / reserved-name error | Sticky **`active_profile`** or **`hermes -p droplet`** | Clear sticky or use **`hermes profile use <real-profile>`**; use **`hermes … droplet`** only with **`droplet` last**. |  
| `hermes droplet` OK only inside repo | Global **`hermes`** without **`scripts/core/`** first on `PATH` | Prepend **`…/hermes-agent/scripts/core`** (and venv **`bin`**) in **`~/.zshrc`**, or always run from the clone with direnv. |  
| **`zsh: command not found: droplet`** | Shell function not loaded | Source **`scripts/shell/hermes-env.sh`** from **`~/.zshrc`** (defines **`droplet()`** → **`ssh_droplet_user.sh`**) or use **`hermes … droplet`** for the CLI hop. |  
| Welcome banner, then **`Warning: Input is not a terminal (fd=0)`**, **`^[[24;1R`**, immediate **`Goodbye`**, SSH disconnect | **`SSH_SUDO_PASSWORD`** + **`sudo -S`**: password is read from a **pipe**, so the **inner** shell’s **stdin** is **not a TTY**; prompt_toolkit exits | **`scripts/core/ssh_droplet.sh`** wraps the remote command with **`exec >/dev/tty 2>&1; exec </dev/tty; …`** after **`sudo -S`** so the Hermes TUI attaches to the **SSH pseudo-tty**. Requires **`ssh -tt`** (already used). |  
| Interactive **sudo** prompts instead of password file | **`SSH_SUDO_PASSWORD`** unset | Set it in **`~/.env/.env`** if you accept storing the admin sudo password there; otherwise type sudo on the **remote** TTY. |
| Slack **`invalid_command_response`** on **`/hermes-*`** | slack-bolt could return the middleware **`BoltResponse`** instead of **`ack.response`** for Socket Mode slash commands (**`process_before_response=False`**) | Fixed in **`gateway/platforms/slack.py`** (**`_ensure_slack_bolt_slash_socket_ack_fix`**); restart the gateway that owns the Slack app token. |
| **`git pull`** on VPS: **merge abort** on **`policies/.pipeline_state/manifest.json`** | Local / pipeline edits in the repo tree on the server | **`git stash push -- policies/.pipeline_state/manifest.json`** (or commit), then **`git pull --ff-only`**. |
| **`Slack app token already in use (PID …)`** / Telegram / WhatsApp scoped locks after a “restart” | A **second** gateway process (often started as **`SSH_USER`** / **`hermesadmin`**) or a leftover process while locks still reference a dead PID | Stop the stray process (e.g. match **`hermesadmin/.../hermes-agent`** + **`gateway run`**). Run production gateway **as `hermesuser`** with **`./venv/bin/hermes -p chief-orchestrator gateway run --replace`** (typically under **`nohup`** or the existing **`gateway-watchdog.sh`**). Confirm with **`hermes -p chief-orchestrator gateway watchdog-check`**. |
| **`hermes gateway restart`** → **`Unit hermes-gateway-….service not found`** | No **systemd user** unit installed for that **`HERMES_HOME`** / profile | Use **`gateway run --replace`** (detached) or **`scripts/core/gateway-watchdog.sh`** as deployed; or run **`hermes gateway install`** for that profile if **`systemctl --user`** is desired. |
| **`profile show`** → **`.env: not configured`** for **chief-orchestrator** while messaging “works” | Secrets only under default **`~/.hermes/.env`** or **`~/hermes-agent/.env`**, not under **`…/profiles/chief-orchestrator/.env`** | Run **`scripts/core/ensure_chief_orchestrator_profile_env.sh`** as **`hermesuser`**; keep a real **`$HERMES_HOME/.env`** for the profile. |

### Step 15 — VPS gateway: operator account, restart, health

**Canonical runtime user on the VPS** is **`hermesuser`** (see **`ssh_droplet.sh`** **`--sudo-user`**). The admin account (**`SSH_USER`**, e.g. **`hermesadmin`**) may have its own **`~/hermes-agent`** clone; starting **`gateway run`** there without **`-p`** and without the same **`.env`** as production produces a gateway with **no platforms enabled** or a **duplicate** that steals **Slack / Telegram / WhatsApp** scoped locks from the real instance.

**Safe patterns**

- **Pull + code update (automation):** Prefer **`ssh_droplet.sh --sudo-user hermesuser 'cd ~/hermes-agent && git pull --ff-only origin main'`** (resolve stash/commit conflicts on **`policies/.pipeline_state/`** if needed).  
- **Restart gateway:** As **`hermesuser`**: **`cd ~/hermes-agent && nohup ./venv/bin/hermes -p chief-orchestrator gateway run --replace >> ~/.hermes/profiles/chief-orchestrator/logs/gateway-restart.log 2>&1 &`** (adjust log path if you standardize elsewhere).  
- **Verify:** **`./venv/bin/hermes -p chief-orchestrator gateway watchdog-check`** — expect exit **0**. By default the check allows **≥1** **`connected=`** platform when Slack/Telegram (etc.) are configured. If **`messaging.watchdog_require_all_platforms: true`** (or **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS=1`**), expect **`all_connected=`** with **every** configured adapter — see **`policies/core/gateway-watchdog.md`** *Repeat implementation checklist*.

**Policy materialization:** run **`policies/core/scripts/start_pipeline.py`** (or your materialize helper) on the server before expecting updated policy trees; the `droplet` suffix only changes **where** the CLI runs.

---

# 16. Key Principle

The quality of this system will be determined by one ordering rule:

**Policies first. Structure second. Security gating third. Agents fourth. Tasks fifth.**

Do not reverse that order.

---

# 17. Minimal Operator Command Sequence

If you want the shortest manual version, do this:

1. give the root agent the canonical pack
2. tell it to generate the registry, chart, lifecycle, task-state, board, channel, audit, alert, remediation, and incident files
3. create Chief Orchestrator
4. create Org Mapper / HR Controller
5. create Chief Security Governor
6. create the core security agents
7. run preflight and audit
8. create Product, Engineering, Operations, and IT / Security Directors if the environment passes
9. create one Project Lead per real project
10. let Project Leads request Workers only as needed
11. review, remediate, and prune regularly

---

# 18. Final Standard

The correct deployment method is:

- define before creating
- register before activating
- secure before expanding
- scope before prompting
- prompt before tasking
- review before expanding
- remediate before normalizing drift
- prune before bloating

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/deployment-handoff.md](deployment-handoff.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
