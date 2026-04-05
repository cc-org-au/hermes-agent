<!-- policy-read-order-nav:top -->
> **Governance read order** — step 18 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/AGENTS.md](AGENTS.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# AGENT_CREATION_WORKFLOW.md — Governed agent creation (three tiers)

This file is the **workspace-local** summary of how new agents are created in the agentic-company model. It is **not** a stub: it encodes binding procedure. If your copy disagrees with `POLICY_ROOT/core/unified-deployment-and-security.md`, **the unified runbook wins** — update this file from repo via materialization, not ad hoc edits.

---

## Three tiers of “creation”

| Tier | What it means | When to use | Registration / tooling |
|------|----------------|------------|-------------------------|
| **1 — Logical agent (same Hermes runtime)** | A role enacted inside one profile: prompts, delegate-tool subagents, narrow tasks. | Extra help without new credentials, gateway, or isolation. | Update `workspace/operations/ORG_REGISTRY.md` / `AGENT_LIFECYCLE_REGISTER.md` when the org treats the role as a **named governed unit**; otherwise document in project charter or archival memory per [`artifacts-and-archival-memory.md`](../../governance/artifacts-and-archival-memory.md). |
| **2 — New Hermes profile (separate runtime)** | A **new** `~/.hermes/profiles/<slug>/` with its own config, secrets, sessions, optional gateway. | Isolation of credentials, messaging identity, or disk state. | `hermes profile create <slug>` (from repo venv). Record **slug ↔ logical role** in `ORG_REGISTRY.md` and `AGENT_LIFECYCLE_REGISTER.md`. See [`deployment-handoff.md`](../../deployment-handoff.md) § Hermes profiles. |
| **3 — Full org spawn (runbook order)** | Chief-directed creation of directors, security agents, project leads, workers per unified deployment phases. | Greenfield expansion after security baseline. | Follow **Recommended Unified Spawn Order** in the unified runbook; every **active** agent is **registered before activation**. |

---

## Mandatory sequence (all tiers that change org truth)

Applies whenever a new **named** agent appears on the org chart or in lifecycle registers.

1. **Define** — name, role title, department, supervisor, project (if any), mission, scope, non-scope, permissions, success metrics, lifecycle = **Proposed**. Security-sensitive: trust level, surfaces, approval gates, WARNING/CRITICAL/safe-mode implications.  
2. **Register** — `ORG_REGISTRY.md` + `AGENT_LIFECYCLE_REGISTER.md` (and security registers if applicable). **No agent becomes Active before registration.**  
3. **Instantiate** — minimal shell: identity, supervisor, department, project, mission, scope, permissions (small context).  
4. **Startup bundle** — identity, scope, boundaries, rules, **current objective** (see unified runbook § *Deliver the Startup Prompt*).  
5. **First task** — concrete mission; avoid overloading startup with long backlogs.

Lifecycle states and hygiene rules: [`agent-lifecycle-org-hygiene-policy.md`](../../governance/standards/agent-lifecycle-org-hygiene-policy.md).

---

## Hermes operator quick reference

- **Same runtime, new “agent”** — Often tier 1: prompts + `delegate_tool`; register only if the role is durable and governed.  
- **Separate bot / secrets / home** — Tier 2: new profile slug; never fake isolation with folders inside one profile.  
- **Re-read** — `POLICY_ROOT/core/unified-deployment-and-security.md` and `POLICY_ROOT/core/deployment-handoff.md` for full checklists.

---

## If this file is missing on disk

Do **not** create a one-line “placeholder” file. Refresh the workspace pack from the repository:

- Run `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` (or `./scripts/materialize_policies_into_hermes_home.sh` for Hermes), **or**  
- Copy `POLICY_ROOT/core/runtime/agent/AGENT_CREATION_WORKFLOW.md` to `WORKSPACE/AGENT_CREATION_WORKFLOW.md` verbatim.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/IDENTITY.md](IDENTITY.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
