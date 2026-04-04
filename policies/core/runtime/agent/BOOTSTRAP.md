<!-- policy-read-order-nav:top -->
> **Governance read order** — step 13 of 56 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/chief-orchestrator-directive.md](../../chief-orchestrator-directive.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# BOOTSTRAP.md — Bootstrapping the agent markdown pack

This file is the **bootstrapping handoff file** for the attached agent markdown pack.

**Scope:** Agentic-company runtime only—not a default assistant configuration.

It is not the first file in the total deployment order.

The total order is:

1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md`
4. `python policies/core/scripts/start_pipeline.py` (see `policies/core/pipeline-runbook.md`)
5. `BOOTSTRAP.md`
6. `AGENTS.md`
7. the remaining attached agent markdown files

This file should be used only after the security-first setup, the unified deployment and security runbook, and the deployment-handoff document have already been followed.

---

## Purpose

This file instigates and explains use of the attached agent markdown files after the builder/runtime deployment handoff has begun.

It does not replace:
- the canonical deployment pack
- the unified runbook
- the deployment-handoff document

It is subordinate to them.

Its purpose is to:
- establish the attached agent markdown pack as the local workspace-level operating layer
- explain what each attached agent markdown file is for
- instruct the user and runtime on how to load and use the pack
- ensure the attached markdown files are used in the correct order

---

## Required Precondition

Before using this file, the following must already have happened:

- the workstation and runtime (VPS) setup from `policies/core/security-first-setup.md`
- the unified operational runbook `policies/core/unified-deployment-and-security.md`
- the deployment handoff from `policies/core/deployment-handoff.md`
- canonical policy and prompt verification
- runtime records initialized or prepared
- security foundation ready for activation

If that has not happened yet, stop and go back to the earlier files.

---

## What this pack does

This pack establishes the local workspace-level operating layer for:
- orchestrator behavior
- project lead behavior
- subagent behavior
- operator profile
- voice/persona continuity
- durable memory conventions
- routing conventions
- token/rate-limit posture
- local tools notes
- periodic human check-ins
- local security summary

This pack should be interpreted as **subordinate workspace operating material**, not as the top-level constitutional layer.

Top-level constitutional layer:
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`

Pipeline and artifact layout (read once per deployment or when paths change):
- `policies/README.md`
- `policies/core/governance/artifacts-and-archival-memory.md`

Workspace operating layer:
- this file
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

---

## First-Run Checklist

Do this in order.

### 1. Confirm the top-level deployment files were already followed
Confirm:
- `policies/core/security-first-setup.md` completed
- `policies/core/unified-deployment-and-security.md` completed
- `policies/core/deployment-handoff.md` completed or being followed
- canonical policies exist
- runbook exists
- runtime records exist or are being initialized

### 2. Deploy or verify the attached agent markdown files
Ensure the following files exist in the workspace-level operating area (under `policies/core/runtime/agent/` in this repository):
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

Runtime placement rule:
- stage canonical policy files under `AGENT_HOME/policies/` (outside workspace, read-mostly)
- keep runtime-editable policy files under `AGENT_HOME/workspace/policies/`
- keep operational registers and project memory under `AGENT_HOME/workspace/operations/`

### 3. Customize operator-facing files
Edit or initialize:
- `USER.md`
- `IDENTITY.md`
- `TOOLS.md`
- `MEMORY.md`

### 4. Register the startup/read order
Ensure the runtime reads the files in the order defined by `AGENTS.md`.

### 5. Keep this file as the local bootstrap handoff
This file should remain present so that future sessions or operators know how the attached pack is meant to be used.

---

## Read Order for the Attached Agent Markdown Pack

After this file, the next file is:

- `AGENTS.md`

That file then defines the startup/read order and session behavior.

The attached markdown pack should then be used in the order defined by `AGENTS.md` (session startup order). Defaults align to:

1. `AGENTS.md`
2. `IDENTITY.md`
3. `USER.md`
4. `SOUL.md`
5. `MEMORY.md`
6. `ORCHESTRATOR.md`
7. `SECURITY.md`
8. `RATE_LIMIT_POLICY.md`
9. `TOOLS.md`
10. `HEARTBEAT.md`
11. `README.md`

The runtime may use a slightly different order only if `AGENTS.md` explicitly defines it.

---

## Dependency and Reference Rules

The attached agent markdown files should reference the broader system as follows:

- constitutional layer:
  - `policies/core/agentic-company-deployment-pack.md`
  - `policies/core/unified-deployment-and-security.md`
- deployment entry layer:
  - `policies/core/security-first-setup.md`
  - `policies/core/unified-deployment-and-security.md`
  - `policies/core/deployment-handoff.md`
- workspace bootstrap layer:
  - `policies/core/runtime/agent/BOOTSTRAP.md`
  - `policies/core/runtime/agent/AGENTS.md`

This prevents the attached markdown pack from floating free from the actual deployment and security architecture.

---

## Final Rule

This file instigates the local agent markdown pack.

It does **not** replace:
- the canonical pack
- the unified runbook
- the deployment-handoff document

Use it exactly as the bridge between the deployment layer and the attached workspace agent files.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/AGENTS.md](AGENTS.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
