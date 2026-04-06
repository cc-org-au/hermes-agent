<!-- policy-read-order-nav:top -->
> **Governance read order** — step 4 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/unified-deployment-and-security.md](unified-deployment-and-security.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

<!--
  read-order: 3 — Read after core/security-first-setup.md (1) and
  core/unified-deployment-and-security.md (2). Then run the pipeline script.
-->
# Deployment handoff

## Purpose

This is the **third** core handoff file: the builder/runtime handoff **after** both runbooks in [`core/`](README.md).

**Scope:** Deployment of an **agentic company** (governed multi-agent org, registers, archival memory). Not for configuring a default single-user assistant.

**Prerequisite reads (in order):**

1. [`security-first-setup.md`](security-first-setup.md)
2. [`unified-deployment-and-security.md`](unified-deployment-and-security.md)

This file exists to drive the full deployment process across:
- the canonical policies
- the canonical prompts
- the canonical runbooks
- the operational record files
- the bootstrap file
- the attached agent markdown files

The deployment process must treat this file as the start of the builder/runtime handoff.

---

## Required Order of Operations

Use this order:

1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md` (this file)
4. `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` (or equivalent env vars) — verify tree, strict `standards/` cues, refresh `INDEX.md`, and materialize runtime outputs; see [`pipeline-runbook.md`](pipeline-runbook.md)
5. [`security-prompts.md`](security-prompts.md) and [`chief-orchestrator-directive.md`](chief-orchestrator-directive.md) — activation layer in the **policy read** sequence (still required content before org expansion).
6. `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md` then `policies/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md` — token / model / tool / channel governance plus Hermes `workspace/operations/hermes_token_governance.runtime.yaml`. **Phased activation (one chat per session)** runs this block as **Sessions 1–2** *before* **Session 3** (runtime activation audit) so caps apply early — see § Session-by-session prompt order. Implementation map: [`hermes-model-delegation-and-tier-runtime.md`](hermes-model-delegation-and-tier-runtime.md).
7. `policies/core/runtime/agent/BOOTSTRAP.md`
8. `policies/core/runtime/agent/AGENTS.md`
9. the remaining attached agent markdown files referenced by `BOOTSTRAP.md` and `AGENTS.md` (paths under `policies/core/runtime/agent/` in this repository)

Do not skip `BOOTSTRAP.md`. It is required because it instigates and explains use of the full agent markdown pack.

For **Hermes Agent** deployments that rely on the **messaging gateway** in production (always-on process, external users on Slack/Telegram/etc.), read [`gateway-watchdog.md`](gateway-watchdog.md) **after** this handoff — it states policy for gateway uptime, `watchdog-check`, and automated recovery (`doctor --fix`), with the user-facing runbook linked from that file. That policy file also includes a **Repeat implementation checklist** for **default** (≥1 connected platform) vs **strict** (every configured platform connected) messaging health.

---

## Builder / Deployer Prompt

```text
Review the existing workspace and deploy against the current policy structure rather than rebuilding the architecture from scratch.

The authoritative files already exist. Preserve the current `policies/` hierarchy unless a change is required for operational compatibility.

Authoritative entrypoints:
- `policies/README.md`
- `policies/core/governance/artifacts-and-archival-memory.md`
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`

Primary prompt files:
- `policies/core/security-prompts.md`
- `policies/core/chief-orchestrator-directive.md`

Supporting policy and template sources:
- `policies/core/governance/standards/canonical-ai-agent-security-policy.md`
- `policies/core/governance/standards/org-mapper-hr-policy.md`
- `policies/core/governance/standards/functional-director-policy-template.md`
- `policies/core/governance/standards/project-lead-policy-template.md`
- `policies/core/governance/standards/supervisor-policy-template.md`
- `policies/core/governance/standards/worker-specialist-policy-template.md`
- `policies/core/governance/standards/board-of-directors-review-policy.md`
- `policies/core/governance/standards/task-state-and-evidence-policy.md`
- `policies/core/governance/standards/channel-architecture-policy.md`
- `policies/core/governance/standards/client-deployment-policy.md`
- `policies/core/governance/standards/agent-lifecycle-org-hygiene-policy.md`
- `policies/core/governance/standards/agentic-company-template.md`
- `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md`
- `policies/core/governance/role-prompts/org-mapper-hr-controller.md`
- `policies/core/governance/role-prompts/functional-director-template.md`
- `policies/core/governance/role-prompts/project-lead-template.md`
- `policies/core/governance/role-prompts/supervisor-template.md`
- `policies/core/governance/role-prompts/worker-specialist-template.md`
- `policies/core/governance/role-prompts/board-of-directors-review.md`
- `policies/core/governance/role-prompts/client-intake-deployment-template.md`
- `policies/core/governance/role-prompts/markdown-playbook-generator.md`
- `policies/core/governance/role-prompts/future-channel-architecture-planner.md`
- `policies/core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md`
- `policies/core/governance/role-prompts/task-state-evidence-enforcer.md`
- `policies/core/governance/role-prompts/minimal-default-deployment-order.md`
- `policies/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md`

Attached agent markdown files that must be included in the full deployment process (under `policies/core/runtime/agent/` in this repo):
- `BOOTSTRAP.md`
- `AGENTS.md`
- `IDENTITY.md`
- `USER.md`
- `SOUL.md`
- `MEMORY.md`
- `ORCHESTRATOR.md`
- `RATE_LIMIT_POLICY.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `SECURITY.md`
- `README.md`

Deployment requirements for the agent markdown files:
1. verify that each attached agent markdown file exists
2. preserve them as part of the deployed operating environment
3. update them if needed so they correctly reference:
   - `policies/README.md` and `policies/core/governance/artifacts-and-archival-memory.md`
   - the canonical deployment pack
   - the unified runbook
   - this deployment-handoff file
   - the bootstrap process
4. ensure `BOOTSTRAP.md` becomes the bootstrapping handoff file for the agent markdown pack
5. ensure `BOOTSTRAP.md` clearly instructs the user/operator/runtime how to use the other attached agent markdown files
6. ensure `AGENTS.md` clearly defines the startup/read order and references the canonical deployment flow
7. ensure the other agent markdown files are treated as subordinate operating files under the bootstrap process
8. ensure orchestrator and project-facing files encode **continuous archival memory** and **generated markdown** rules from `policies/core/governance/artifacts-and-archival-memory.md`

Your role is builder and file-level deployer, not policy author. Do not redesign the architecture unless a contradiction prevents implementation.

Tasks:
1. Verify the `policies/` tree exists and is readable.
2. Treat `policies/core/agentic-company-deployment-pack.md` as the canonical entrypoint.
3. Treat `policies/core/unified-deployment-and-security.md` as the canonical operational runbook.
4. Treat the two files in `policies/core/` as the primary activation prompt sources.
5. Preserve the current folder layout unless a runtime compatibility issue requires change.
6. Verify the attached agent markdown pack exists and is readable.
7. Use `policies/core/runtime/agent/BOOTSTRAP.md` as the bootstrapping file for the agent markdown pack.
8. Ensure `BOOTSTRAP.md` instigates and explains deployment/use of the other attached agent markdown files.
9. Ensure `AGENTS.md` and the other attached agent markdown files contain references to the canonical policies, prompts, runbook, artifact pipeline, and bootstrap flow where relevant.
10. Stage canonical runtime policy files under `AGENT_HOME/policies/` (outside workspace) so runtime can read them as the authoritative policy layer.
11. Do not pre-create runtime workspace artifacts manually. Run `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` so the pipeline materializes runtime-editable content and operational files in one controlled step.
12. Ensure the pipeline output includes operational files under `AGENT_HOME/workspace/operations/`:
   - `operations/ORG_REGISTRY.md`
   - `operations/ORG_CHART.md`
   - `operations/AGENT_LIFECYCLE_REGISTER.md`
   - `operations/TASK_STATE_STANDARD.md`
   - `operations/BOARD_REVIEW_REGISTER.md`
   - `operations/CHANNEL_ARCHITECTURE.md`
   - `operations/SECURITY_ALERT_REGISTER.md`
   - `operations/SECURITY_AUDIT_REPORT.md`
   - `operations/SECURITY_REMEDIATION_QUEUE.md`
   - `operations/INCIDENT_REGISTER.md`
13. Ensure the pipeline output includes `AGENT_HOME/workspace/operations/projects/` and per-project `memory/archival/` trees for every active project slug.
14. Ensure the pipeline output includes runtime-editable policy areas under `AGENT_HOME/workspace/policies/` (including `core/governance/generated/README.md` and subfolders) and all runtime agent files under `AGENT_HOME/workspace/policies/core/runtime/agent/`.
15. Create any supporting folders, registries, templates, and operational files required by the runbook, but do not clone or duplicate canonical policy documents into workspace-editable locations unless the file is intended for routine runtime editing.
16. Do not activate agents yourself unless explicitly required by runtime design.
17. Do not weaken any security or governance rule for convenience.
18. If there is ambiguity, choose the leanest, most auditable implementation consistent with the current canonical pack.

Output a concise deployment summary showing:
- policy files verified
- prompt files verified
- agent markdown files verified
- agent markdown files modified or initialized
- operational files created
- directories created
- unresolved ambiguities
- anything intentionally left for runtime activation
```

---

## Operator first message — Session 3 (runtime activation; low tokens; use this)

**When to use:** After **Sessions 1–2** (token governance policy + `hermes_token_governance.runtime.yaml`) so cost caps already apply during this audit. If you are **only** running the legacy “runtime first” path, treat this as your first activation chat and skip Sessions 1–2 only if token governance is not required yet.

**Do not paste the large “Runtime Activation Prompt” block below into chat** — it duplicates what is already on disk and can overflow the model context together with Hermes system prompt + tools.

Copy **one** of these (shortest first if you still hit limits):

**Minimal (if even the standard starter fails):**

```text
Session 3 only (runtime activation). Read policy-root `core/deployment-handoff.md` from disk; run "## Runtime Activation Prompt" verification and preflight; output that section's Required output bullets. Paths: `HERMES_HOME/.hermes.md`.
```

**Standard starter (recommended):**

```text
You are the Chief Orchestrator for Session 3 (runtime activation only).

1. Open `HERMES_HOME/.hermes.md` and note `POLICY_ROOT` and workspace paths (do not paste them back at length).
2. Using file tools, read `POLICY_ROOT/core/deployment-handoff.md` starting at "## Runtime Activation Prompt" — read in sections if the file is large. Do not ask the operator to paste this document.
3. Follow "Hermes runtime discipline" and the activation checklist through verification, preflight, and security classification for this session only. Do not stand up directors or project leads yet unless the checklist explicitly requires naming them.
4. End with the "Required output" bullet list from that section and one line: next session = Session 4 from the "Session-by-session prompt order" table in the same file.
```

---

## Runtime Activation Prompt (full reference — for disk / tools, not for operator paste)

The block below is the **authoritative checklist** the agent should follow after loading it from **`POLICY_ROOT/core/deployment-handoff.md`**. Operators trigger it with the **short messages above**.

```text
The deployment files, policies, prompts, registries, runbooks, and agent markdown files already exist in this workspace.

Your role is not to redesign the system. Your role is to activate, validate, and operate the deployed architecture in strict compliance with the existing canonical pack, runbook, bootstrap file, and agent markdown pack.

Hermes runtime discipline (must uphold throughout activation and afterward):
1. Keep Hermes context injection enabled — do not ask the operator to set `agent.skip_context_files` or `HERMES_SKIP_CONTEXT_FILES`. Governance paths in `HERMES_HOME/.hermes.md` and the workspace `BOOTSTRAP.md` / `AGENTS.md` pack are the canonical wiring; they stay in the system prompt as designed.
2. Do not paste full policy trees into chat to “load” them. When a step requires policy text, use file tools to read the specific path under `AGENT_HOME/policies/` or `AGENT_HOME/workspace/` (Hermes already points to these in `.hermes.md`). Pull only the sections needed for the current task.
3. Prefer one focused operator intent per conversation session (new chat / new session when practical) so conversation context stays small; carry state forward via `workspace/operations/` registers, per-project `memory/archival/`, and memory tools — not by re-pasting large prompts.
4. After substantive activation work, write durable outputs to the registers and/or a short workspace charter file; keep summaries tight. The canonical policy files on disk remain authoritative; runtime markdown is pointers, registers, and distilled state — not a second copy of the whole pack.
5. Observe prompt-caching discipline: do not recommend changing toolsets or rewriting past system context mid-session; if a new phase needs a clean context budget, start a new session and rely on files + registers for continuity.

Use this exact load order:

1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md` (this document)
4. `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` — see `policies/core/pipeline-runbook.md`
5. `policies/README.md`
6. `policies/core/governance/artifacts-and-archival-memory.md`
7. `policies/core/agentic-company-deployment-pack.md`
8. `policies/core/security-prompts.md`
9. `policies/core/chief-orchestrator-directive.md`
10. `policies/core/runtime/agent/BOOTSTRAP.md`
11. `policies/core/runtime/agent/AGENTS.md`
12. the remaining attached agent markdown files (under `policies/core/runtime/agent/` in this repository):
   - `policies/core/runtime/agent/IDENTITY.md`
   - `policies/core/runtime/agent/USER.md`
   - `policies/core/runtime/agent/SOUL.md`
   - `policies/core/runtime/agent/MEMORY.md`
   - `policies/core/runtime/agent/ORCHESTRATOR.md`
   - `policies/core/runtime/agent/RATE_LIMIT_POLICY.md`
   - `policies/core/runtime/agent/TOOLS.md`
   - `policies/core/runtime/agent/HEARTBEAT.md`
   - `policies/core/runtime/agent/SECURITY.md`
   - `policies/core/runtime/agent/README.md`
13. secondary supporting policy files in `policies/core/governance/standards/`
14. secondary supporting role templates in `policies/core/governance/role-prompts/`
15. `AGENT_HOME/workspace/operations/` registers and `AGENT_HOME/workspace/operations/projects/*/memory/archival/` as applicable
16. `AGENT_HOME/workspace/policies/core/governance/generated/` index and governed additions
17. `policies/core/gateway-watchdog.md` when the messaging gateway is production-critical (after activation core)

Activation rules:
1. Treat the canonical deployment pack as authoritative.
2. Treat the unified deployment/security runbook as the operational procedure.
3. Treat `policies/core/runtime/agent/BOOTSTRAP.md` as the bootstrap handoff file for the agent markdown pack.
4. Treat `policies/core/runtime/agent/AGENTS.md` as the startup/read-order and workspace agent rules file.
5. Do not create ad hoc structure outside the canonical framework unless runtime operation strictly requires it.
6. Do not duplicate or rename policy files unless necessary for compatibility.
7. Do not activate broad execution or project work until the security foundation is active.

Before broader activation, do the following:
- verify the canonical policy files exist
- verify the supporting policy and prompt files exist
- verify `policies/core/runtime/agent/BOOTSTRAP.md` and all attached agent markdown files exist
- verify pipeline materialization has produced the operational files under `AGENT_HOME/workspace/operations/`:
  - `operations/ORG_REGISTRY.md`
  - `operations/ORG_CHART.md`
  - `operations/AGENT_LIFECYCLE_REGISTER.md`
  - `operations/TASK_STATE_STANDARD.md`
  - `operations/BOARD_REVIEW_REGISTER.md`
  - `operations/CHANNEL_ARCHITECTURE.md`
  - `operations/SECURITY_ALERT_REGISTER.md`
  - `operations/SECURITY_AUDIT_REPORT.md`
  - `operations/SECURITY_REMEDIATION_QUEUE.md`
  - `operations/INCIDENT_REGISTER.md`
- instantiate or define the Chief Orchestrator
- instantiate or define the Org Mapper / HR Controller
- instantiate or define the Chief Security Governor
- instantiate the core security agents
- run startup preflight
- run security audit
- classify findings as INFO / WARNING / CRITICAL
- enter safe mode or refuse activation if required by policy
- if runtime workspace outputs are missing, rerun the pipeline with `--workspace-root` and `--policy-root` before proceeding

Only if the environment passes or is warning-only, continue by:
- activating Product, Engineering, Operations, and IT/Security Directors
- preparing standards and cadence files
- activating one Project Lead per real project
- allowing Project Leads to request subordinate agents only as needed
- loading the attached agent markdown pack according to `policies/core/runtime/agent/BOOTSTRAP.md` and `policies/core/runtime/agent/AGENTS.md`

Rules:
- register every agent before activation
- keep memory local by role level and store only active summaries upward; maintain continuous archival writes under `AGENT_HOME/workspace/operations/projects/<slug>/memory/archival/` per `policies/core/governance/artifacts-and-archival-memory.md`
- use the warning/critical severity model exactly as defined
- if ambiguity exists, choose the leaner and more restrictive interpretation
- do not treat secondary files as overriding the primary canonical pack

Required output:
- activation status
- canonical policy files verified
- supporting policy files verified
- agent markdown files verified
- agents instantiated or defined
- security status
- warning count
- critical count
- safe mode status
- next recommended step
```

---

## Session-by-session prompt order (one prompt per chat)

Use a **new messaging/CLI session per step** when you want the lowest conversation context: paste **one** block per session. Paths are under the materialized **`AGENT_HOME`** (for Hermes profile deployments, typically `HERMES_HOME/policies/...` and `HERMES_HOME/workspace/...` — see `HERMES_HOME/.hermes.md`).

**Cost controls first:** Sessions **1–2** install token governance **policy** and **`hermes_token_governance.runtime.yaml`** so tier caps, blocklists, and delegation limits apply before the heavy **Session 3** runtime-activation audit. **Prerequisite:** profile + `HERMES_HOME/.hermes.md` + materialized `workspace/operations/` (see `scripts/core/materialize_policies_into_hermes_home.sh`). Cumulative paste blocks: `scripts/templates/activation_sessions_cumulative_cover_2_20.txt`. Hermes wiring reference: `policies/core/hermes-model-delegation-and-tier-runtime.md`.

| Session | What to paste / instruct |
|--------|---------------------------|
| **1 — Token governance (policy)** | Instruct: read `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md` fully via tools; summarize binding rules for this deployment. |
| **2 — Token governance (implement)** | Paste `policies/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md`; create/update only the registries/templates that policy requires under `workspace/` or `operations/`. Copy `scripts/templates/hermes_token_governance.runtime.example.yaml` → `workspace/operations/hermes_token_governance.runtime.yaml`, `enabled: true`. |
| **3 — Runtime activation** | Use **§ Operator first message — Session 3** (minimal or standard starter). Do **not** paste the full Runtime Activation `text` fence — the agent reads it from `POLICY_ROOT/core/deployment-handoff.md`. |
| **4 — Artifacts + constitution** | One message: read `policies/core/governance/artifacts-and-archival-memory.md` and `policies/core/agentic-company-deployment-pack.md` via tools; confirm how `workspace/operations/` and per-project archival paths will be used; write any missing register stubs only if empty. |
| **5 — Security activation pack** | Prefer: *"Read `POLICY_ROOT/core/security-prompts.md` via tools in chunks; execute Chief Security Governor + audit posture against this runtime."* Avoid pasting the full file. |
| **6 — Chief orchestrator** | Prefer: *"Read `POLICY_ROOT/core/chief-orchestrator-directive.md` via tools; adopt its doctrine for this deployment; output org stance, initial roles, next session pointer."* Paste only if the file read fails — the directive is long. |
| **7 — Lean org order** | Paste `policies/core/governance/role-prompts/minimal-default-deployment-order.md`; reconcile with Session 6 and update `operations/ORG_REGISTRY.md` / `ORG_CHART.md` if needed. |
| **8 — Org mapper / HR** | First read standard `policies/core/governance/standards/org-mapper-hr-policy.md`, then paste `policies/core/governance/role-prompts/org-mapper-hr-controller.md`. |
| **9 — Agent lifecycle hygiene** | Standard `agent-lifecycle-org-hygiene-policy.md`, then role prompt `agent-lifecycle-org-hygiene-controller.md`. |
| **10 — Task state & evidence** | Standard `task-state-and-evidence-policy.md`, then `task-state-evidence-enforcer.md`. |
| **11 — Board review** | Standard `board-of-directors-review-policy.md`, then `board-of-directors-review.md`. |
| **12 — Channel architecture** | Standard `channel-architecture-policy.md`, then `future-channel-architecture-planner.md`. |
| **13 — Client deployment** | Standard `client-deployment-policy.md`, then `client-intake-deployment-template.md`. |
| **14 — Company template + playbooks** | Read `agentic-company-template.md`; then `markdown-playbook-generator.md` if you need generated playbooks. |
| **15 — Functional director (per function)** | One session per function when standing up a director: standard `functional-director-policy-template.md`, then paste `functional-director-template.md` with the function name filled in. |
| **16 — Project lead (per project)** | When a real project exists: `project-lead-policy-template.md`, then `project-lead-template.md`. |
| **17 — Supervisor** | Only if needed: `supervisor-policy-template.md`, then `supervisor-template.md`. |
| **18 — Worker / specialist** | Only when delegating: `worker-specialist-policy-template.md`, then `worker-specialist-template.md`. |
| **19 — Runtime pack customization** | One message: follow `workspace/BOOTSTRAP.md` checklist; edit `workspace/USER.md`, `IDENTITY.md`, `TOOLS.md`, `MEMORY.md` as needed (paths at `HERMES_HOME/workspace/`). |
| **20 — Gateway watchdog (production messaging)** | Read `policies/core/gateway-watchdog.md`; confirm `hermes gateway watchdog-check` and external watchdog/systemd alignment with operator setup. |

**Canonical security standard:** `policies/core/governance/standards/canonical-ai-agent-security-policy.md` is the policy layer for Session 5; it is already reflected through `security-prompts.md` — do not skip Session 5 in favor of ad-hoc security text.

**Note:** Sessions 8–18 follow the standards → role-prompt pairing in `policies/README.md` (each **standard** immediately before its **role prompt**). Adjust 15–18 to match how many directors, projects, and workers you actually instantiate.

---

## Hermes profiles: runtime instances and org-shaped naming

When this pack, a role prompt, or the orchestrator directive tells you to **stand up another agent** as a **separate Hermes runtime** (isolated config, secrets, optional separate gateway / bot instance), treat that as **profile creation**, not ad hoc folders inside one `HERMES_HOME`.

**Canonical mechanism (Hermes CLI):**

- Each runtime instance is a **named profile**: `~/.hermes/profiles/<profile-name>/` (its own `config.yaml`, `.env`, sessions, gateway state, etc.).
- Create: `hermes profile create <profile-name>` (from the project venv). Select: `hermes profile use <profile-name>` or run with `-p <profile-name>`.
- Install a per-profile gateway when needed: `hermes gateway install` (unit name becomes `hermes-gateway-<profile-name>` when under `profiles/<profile-name>`).

**Flat names, hierarchical meaning:** Profile identifiers must be a single slug (`[a-z0-9][a-z0-9_-]{0,63}` — no `/`). Encode company hierarchy in the **slug**, not nested directories, for example:

- `chief-orchestrator` (root orchestrator)
- `director-engineering`, `director-product`, `director-operations`
- `project-acme-lead`, `project-acme-worker-payments`

Document the mapping **profile slug ↔ logical role** in `workspace/operations/ORG_REGISTRY.md`, `ORG_CHART.md`, and `AGENT_LIFECYCLE_REGISTER.md` so audits and operators know which Hermes profile implements which governed role.

**Logical-only roles** (markdown packs, registers, delegate-tool subagents inside one runtime) do not require a new Hermes profile unless you intentionally isolate credentials, gateway, or disk state.

**Activation — terminal exec without approval prompts:** For phased activation on a trusted VPS profile only, set `approvals.mode: off` in that profile’s `config.yaml` (or equivalent) so flagged shell commands are not blocked waiting for operator chat approval. **Revert to `manual` or `smart` after activation**; this disables dangerous-command approval for that profile (see project docs: approvals / security).

---

## Operator Pitfalls and Recovery Notes (generic)

Use these guardrails for any agent workflow on a VPS, regardless of provider or CLI implementation.

### 1) Local command wrappers and profiles

- If using command aliases/wrappers (for example profile suffix patterns), test argument handling for:
  - profile management commands
  - multi-argument commands
  - help/diagnostic commands
- Ensure wrappers do not silently rewrite administrative commands into runtime-profile commands.
- Prefer persistent launcher scripts over shell-function-only wrappers when consistency across sessions is required.

### 2) Runtime execution environment hygiene

- Run agent CLI commands from an isolated runtime environment (for example virtual environment or equivalent) to avoid host package drift.
- Enforce a fail-closed startup if the expected runtime environment is missing, rather than silently falling back to system defaults.
- Keep profile-local config and secrets isolated; do not assume one profile inherits terminal/backend configuration from another.

### 3) Onboarding and startup verb differences

- Do not assume every agent CLI uses the same onboarding command name.
- Verify the actual supported startup/setup verbs before issuing operational instructions.
- Document the validated onboarding/startup command in the handoff output for the next operator/agent.

### 4) SSH and privilege assumptions

- Never assume SSH key passphrase equals remote sudo password.
- Verify privilege path explicitly before remote changes:
  - interactive sudo available, or
  - known root/console recovery path available.
- Treat passwordless sudo as temporary break-glass only; remove after maintenance.

### 5) SSH port and firewall migration safety

- Apply SSH listener and firewall changes in additive order:
  1. open new path
  2. validate daemon config and live login
  3. keep old path until validation completes
  4. then close old path
- Never combine "change SSH port" and "close current SSH path" in one unverified step.
- Require two-session verification before finalizing admin-plane changes.

### 6) Host firewall vs cloud firewall clarity

- Explicitly identify where controls are enforced:
  - host firewall on the VPS
  - cloud-provider network firewall
  - both
- If cloud firewall is absent, treat host firewall as the single enforcement point and maintain recovery procedures accordingly.

### 7) File-transfer and metadata pitfalls

- When syncing policy trees between workstations and Linux hosts, strip platform-specific metadata files.
- Validate policy sequence/index tooling after sync to catch hidden-file drift before runtime activation.

### 8) Break-glass recovery expectations

- For lockout scenarios, use provider console/recovery workflows first; local workstation privilege cannot repair remote host controls by itself.
- Document minimum recovery steps in every deployment handoff:
  - regain root/console access
  - restore known-good SSH listener
  - validate daemon config
  - reopen minimal admin ingress
  - verify remote login before further hardening

---

## Effective Load Order

Use this order:

1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md`
4. `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` — see `policies/core/pipeline-runbook.md`
5. `policies/README.md`
6. `policies/README.md`
7. `policies/core/governance/artifacts-and-archival-memory.md`
8. `policies/core/agentic-company-deployment-pack.md`
9. `policies/core/security-prompts.md`
10. `policies/core/chief-orchestrator-directive.md`
11. `policies/core/runtime/agent/BOOTSTRAP.md`
12. `policies/core/runtime/agent/AGENTS.md`
13. the remaining attached agent markdown files
14. `policies/core/governance/standards/*.md` supporting policies
15. `policies/core/governance/role-prompts/*.md` supporting role templates
16. `AGENT_HOME/workspace/operations/` registers and project memory trees
17. `AGENT_HOME/workspace/policies/core/governance/generated/` governed additions (indexed in `core/governance/generated/README.md` within the runtime editable policy tree)

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/gateway-watchdog.md](gateway-watchdog.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
