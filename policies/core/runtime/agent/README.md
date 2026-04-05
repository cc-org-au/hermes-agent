<!-- policy-read-order-nav:top -->
> **Governance read order** — step 28 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/HEARTBEAT.md](HEARTBEAT.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# README.md — Agent workflow pack index

This is the human-facing index for the attached agent markdown pack.

**Scope:** These files configure the **agentic company** runtime (governed agents, project isolation, archival memory). They are not a substitute for a single generic assistant profile.

Use this order:

1. `policies/core/security-first-setup.md`
2. `policies/core/unified-deployment-and-security.md`
3. `policies/core/deployment-handoff.md`
4. `python policies/core/scripts/start_pipeline.py` — see `policies/core/pipeline-runbook.md`
5. `policies/core/security-prompts.md` and `policies/core/chief-orchestrator-directive.md`
6. `policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md` then `policies/core/governance/role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md`
7. `policies/core/runtime/agent/BOOTSTRAP.md`
8. `policies/core/runtime/agent/AGENTS.md`
9. the remaining attached agent markdown files

The attached markdown pack is the workspace operating layer and is subordinate to:
- `policies/README.md`
- `policies/core/governance/artifacts-and-archival-memory.md`
- `policies/core/agentic-company-deployment-pack.md`
- `policies/core/unified-deployment-and-security.md`

## Contents

| File | Role |
|------|------|
| `BOOTSTRAP.md` | Bootstrapping handoff for the attached pack |
| `AGENTS.md` | Startup order and workspace agent rules |
| `AGENT_CREATION_WORKFLOW.md` | Governed agent creation (logical / new profile / runbook order); no placeholders |
| `IDENTITY.md` | Agent persona |
| `USER.md` | Operator profile template |
| `SOUL.md` | Voice and continuity |
| `MEMORY.md` | Orchestrator-level durable memory |
| `ORCHESTRATOR.md` | Routing and isolation |
| `RATE_LIMIT_POLICY.md` | Token/rate-limit posture |
| `TOOLS.md` | Local environment cheat sheet |
| `HEARTBEAT.md` | Periodic check template |
| `SECURITY.md` | Local security summary |

Use `policies/core/runtime/agent/BOOTSTRAP.md` to start the local pack (or `BOOTSTRAP.md` at workspace root if the pack was copied out of `policies/core/runtime/agent/`).

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/standards/canonical-ai-agent-security-policy.md](../../governance/standards/canonical-ai-agent-security-policy.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
