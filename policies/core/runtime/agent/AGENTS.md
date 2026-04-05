<!-- policy-read-order-nav:top -->
> **Governance read order** — step 17 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/BOOTSTRAP.md](BOOTSTRAP.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# AGENTS.md — Workspace agent rules and startup order

This file defines the startup/read order and the local workspace rules for the attached agent markdown pack.

**Scope:** This pack implements the **agentic company** operating layer (orchestrator, project leads, governed subagents, security gating). It is **not** a generic single-user assistant profile.

It is **not** the first file in the total system order.

Total deployment order:
1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md`
4. Run `python policies/core/scripts/start_pipeline.py` (or `./policies/start_pipeline.sh`) so `INDEX.md` and verification match the tree — see `policies/core/pipeline-runbook.md`
5. `policies/core/security-prompts.md` and `policies/core/chief-orchestrator-directive.md`
6. `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md` then `policies/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md`
7. `policies/core/runtime/agent/BOOTSTRAP.md`
8. `policies/core/runtime/agent/AGENTS.md`
9. the remaining attached agent markdown files under `policies/core/runtime/agent/` (or the same filenames at workspace root if the pack was copied there)

This file is subordinate to:
- `policies/README.md` (policies tree index and pipeline)
- `policies/core/governance/artifacts-and-archival-memory.md` (generated docs, registers, per-project memory)
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`
- `policies/core/deployment-handoff.md`
- `policies/core/runtime/agent/BOOTSTRAP.md`

If any local workspace rule conflicts with the canonical policy layer, the canonical layer wins.

---

## Session Startup Order

On each new session, use this order:

1. Read `IDENTITY.md`
2. Read `USER.md`
3. Read `SOUL.md`
4. Read `MEMORY.md` if present
5. Read `ORCHESTRATOR.md` if acting as orchestrator or project lead
6. Read `SECURITY.md` if security, trust, exposure, or permission boundaries are relevant
7. Read `RATE_LIMIT_POLICY.md` if long-running context or compaction is relevant
8. Read `TOOLS.md` only if host/local-environment-specific facts are needed
9. Use `HEARTBEAT.md` only for periodic human check-ins
10. Use `README.md` only as a human-facing index/reference if needed
11. Read `AGENT_CREATION_WORKFLOW.md` before **registering** a new governed agent, changing `AGENT_LIFECYCLE_REGISTER.md` / `ORG_REGISTRY.md` for a new role, or creating a **separate Hermes profile** for a role

If any pack file is missing from `WORKSPACE/`, **re-materialize** from the repository (`policies/core/scripts/start_pipeline.py` with `--workspace-root`, or `scripts/materialize_policies_into_hermes_home.sh` for Hermes), or copy the matching file from `POLICY_ROOT/core/runtime/agent/`. **Do not** write placeholder markdown (e.g. “TBD”, “placeholder”, “document missing”) as a substitute for a governed pack file — that breaks audits and contradicts canonical policy.

---

## Role of This File

This file exists to:
- define the local startup/read order
- keep the workspace pack aligned to the canonical deployment architecture
- prevent local markdown files from being treated as a separate constitutional layer
- keep memory, tools, routing, and tone behavior consistent

---

## Memory & Files

- Orchestrator durable **active** state lives in `MEMORY.md` (summaries and pointers only).
- **Project-specific** durable memory, archival logs, and recall-oriented files live under `AGENT_HOME/workspace/operations/projects/<project_slug>/` per `policies/core/governance/artifacts-and-archival-memory.md`. Never mix project trees.
- Every agent with a project affiliation must **append archival memory** (decisions, evidence pointers, handoff notes) on a **continuous cadence**—at minimum end of substantive work units and before context compaction—not only when asked.
- Do not store secrets in `MEMORY.md` or in archival files.
- Do not treat local workspace files as permission to violate the canonical security baseline

---

## Orchestration Model

- Orchestrator coordinates
- Project leads own isolated project work
- Subagents are scoped and disposable
- Isolation is mandatory
- One project’s paths, secrets, and durable state must not bleed into another

The canonical orchestration, security, and activation logic still comes from the canonical pack and unified runbook.

---

## Security Reference

For local workspace security posture, read `SECURITY.md`.

For canonical security posture, rely on:
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`

The local workspace files do not weaken those controls.

---

## Execution Integrity

- Do not claim a command or deploy succeeded unless it actually ran and was verified in-session
- Separate completed vs not completed steps
- Distinguish local vs remote actions
- Do not let local workspace convenience override the canonical trust model

---

## Final Rule

This file controls the local workspace pack startup order.

It is the file that follows `policies/core/runtime/agent/BOOTSTRAP.md`.

It must always be interpreted inside the broader canonical deployment and security framework.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/AGENT_CREATION_WORKFLOW.md](AGENT_CREATION_WORKFLOW.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
