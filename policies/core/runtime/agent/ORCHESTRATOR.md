<!-- policy-read-order-nav:top -->
> **Governance read order** — step 21 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/MEMORY.md](MEMORY.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# ORCHESTRATOR.md — Top-level routing and isolation

This file is part of the attached workspace agent markdown pack.

**Scope:** Agentic-company orchestration—not generic single-user task routing.

Read it after `AGENTS.md` when acting as orchestrator or project lead.

It provides local workspace routing guidance only.

## Rules
1. Never load full repositories into orchestrator context
2. Route deep work to the correct project lead or scoped subagent
3. Maintain isolation across projects; project state lives under `AGENT_HOME/workspace/operations/projects/<project_slug>/` per `policies/core/governance/artifacts-and-archival-memory.md`
4. Do not let local routing convenience override the canonical security model
5. If security gating has not been completed, do not proceed to broader project activation
6. Before major decisions, verify recent `AGENT_HOME/workspace/operations/projects/<slug>/memory/archival/` entries for involved projects

This file depends on:
- `policies/core/runtime/agent/BOOTSTRAP.md`
- `policies/core/runtime/agent/AGENTS.md`
- `policies/core/runtime/agent/MEMORY.md`

And is subordinate to:
- `policies/README.md`
- `policies/core/governance/artifacts-and-archival-memory.md`
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`
- `policies/core/deployment-handoff.md`

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/SECURITY.md](SECURITY.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
