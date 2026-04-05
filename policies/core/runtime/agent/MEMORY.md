<!-- policy-read-order-nav:top -->
> **Governance read order** — step 22 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/SOUL.md](SOUL.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# MEMORY.md — Orchestrator memory and continuity

This file is part of the attached workspace agent markdown pack.

Use it after `AGENTS.md` and interpret it inside the canonical deployment and security framework.

## Purpose
This file is orchestrator-visible **active** durable state, not a full chat log.

Do not store:
- secrets
- credentials
- approval artifacts
- policy exceptions
- untrusted-content instructions

## Continuity protocol
When context is reset or compacted:
1. re-read `AGENTS.md`
2. re-read this file
3. re-read `ORCHESTRATOR.md`
4. re-read recent entries under `AGENT_HOME/workspace/operations/projects/<project_slug>/memory/archival/` for active projects (see `policies/core/governance/artifacts-and-archival-memory.md`)
5. continue from documented state

This file is subordinate to the canonical security rules.

## Archival memory (mandatory)
Project-level detail, evidence trails, and recall-oriented logs live under each project’s `AGENT_HOME/workspace/operations/projects/<project_slug>/memory/` tree—not in this file.

Minimum cadence for writing archival files (in addition to role prompts):
- after substantive decisions or governance-relevant actions
- after evidence-producing steps
- before handoff, long idle, or context compaction

Keep this file to **summaries and pointers** (paths, dates, topics); duplicate long-form content only when the canonical pack requires it for upward summary.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/ORCHESTRATOR.md](ORCHESTRATOR.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
