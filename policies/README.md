<!-- policy-read-order-nav:top -->
> **Governance read order** — step 9 of 56 in the canonical `policies/` sequence (layer map & tables: [`README.md`](README.md)).
> **Before this file:** read [core/global-agentic-company-deployment-policy.md](core/global-agentic-company-deployment-policy.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Policies — agentic company workspace

This directory is the **governance “brain”** for a multi-agent company. It is **not** a generic assistant profile.

**Layout:** Almost all policy material lives under **[`core/`](core/README.md)** — runbooks, [`deployment-handoff.md`](core/deployment-handoff.md), [`pipeline-runbook.md`](core/pipeline-runbook.md) (tooling), activation prompts, **runtime** agent pack, **governance** (standards, role-prompts, generated), and **scripts** (tooling). Only this file, [`INDEX.md`](INDEX.md), and [`.pipeline_state/`](.pipeline_state/) sit at `policies/` root so agents can find the map in one place.

**Navigation:** Each markdown file has a **step N of M** banner and a **next step** line. The sequence is [`READ_ORDER_SEQUENCE`](core/scripts/apply_read_order_navigation.py) in `apply_read_order_navigation.py`. Run `python policies/core/scripts/start_pipeline.py` to refresh nav blocks and [`INDEX.md`](INDEX.md).

---

## Layer model (inside `core/`)

Read **top to bottom** within `core/`: siblings at the same depth are ordered by the step tables below. Deeper paths are generally **later** in the rollout.

| Section | Path | Role |
|---------|------|------|
| **Runbooks & authority** | [`core/`](core/README.md) (root files: `security-first-setup.md`, `unified-deployment-and-security.md`, `deployment-handoff.md`, [`gateway-watchdog.md`](core/gateway-watchdog.md), deployment packs, `pipeline-runbook.md`, activation prompts) | Trust boundaries, constitutional packs, pipeline entry, messaging uptime policy, activation — **read first** within `core/`. |
| **Runtime** | [`core/runtime/agent/`](core/runtime/agent/BOOTSTRAP.md) | Workspace agent pack (session behavior). |
| **Governance** | [`core/governance/`](core/governance/artifacts-and-archival-memory.md) | Standards, role-prompts, generated markdown, artifacts/archival rules for `operations/`. |
| **Tooling** | [`core/scripts/`](core/scripts/README.md) | Verify, index, pipeline — not policy prose. |

For runtime deployments, `operations/` should live under `AGENT_HOME/workspace/memory/runtime/operations/` (see [`core/governance/artifacts-and-archival-memory.md`](core/governance/artifacts-and-archival-memory.md)). A repository-root `operations/` tree is acceptable only for local development or source-controlled bootstrapping.

---

## Canonical read order (tables)

### A — Runbooks, packs, launch (under `core/`)

| Step | File | Notes |
|------|------|--------|
| A1 | [`core/security-first-setup.md`](core/security-first-setup.md) | Workstation/VPS trust — **first** |
| A2 | [`core/unified-deployment-and-security.md`](core/unified-deployment-and-security.md) | Unified deployment + security |
| A3 | [`core/deployment-handoff.md`](core/deployment-handoff.md) | Builder/runtime handoff |
| A3b | [`core/gateway-watchdog.md`](core/gateway-watchdog.md) | Messaging gateway uptime & recovery (watchdog / doctor) for production |
| A4 | [`core/README.md`](core/README.md) | What lives in `core/` |
| A5 | [`core/agentic-company-deployment-pack.md`](core/agentic-company-deployment-pack.md) | Constitutional pack |
| A6 | [`core/global-agentic-company-deployment-policy.md`](core/global-agentic-company-deployment-policy.md) | Global deployment policy |
| A7 | **This** [`README.md`](README.md) | Repo-level map (you are here) |
| A8 | [`core/pipeline-runbook.md`](core/pipeline-runbook.md) | Run `start_pipeline.py` |
| A9–A10 | [`core/security-prompts.md`](core/security-prompts.md), [`core/chief-orchestrator-directive.md`](core/chief-orchestrator-directive.md) | Activation |

### B — Runtime agent pack

| Step | File | Notes |
|------|------|--------|
| B1 | [`core/runtime/agent/BOOTSTRAP.md`](core/runtime/agent/BOOTSTRAP.md) | Then [`AGENTS.md`](core/runtime/agent/AGENTS.md) and the rest of `core/runtime/agent/` |

### C — Governance

Read each [`core/governance/standards/`](core/governance/standards/canonical-ai-agent-security-policy.md) file with its linked prompt under [`core/governance/role-prompts/`](core/governance/role-prompts/org-mapper-hr-controller.md). Then [`core/governance/artifacts-and-archival-memory.md`](core/governance/artifacts-and-archival-memory.md) and [`core/governance/generated/`](core/governance/generated/README.md) as needed.

---

## Before you run anything

1. Read both runbooks under [`core/`](core/README.md) in order (`security-first-setup` → `unified-deployment-and-security` → `deployment-handoff`).
2. Run `python policies/core/scripts/start_pipeline.py` when you need a verified tree and fresh `INDEX.md`.

```bash
python policies/core/scripts/start_pipeline.py --dry-run
python policies/core/scripts/start_pipeline.py
./policies/start_pipeline.sh
```

---

## Precedence

1. Human operator explicit instruction  
2. [`core/agentic-company-deployment-pack.md`](core/agentic-company-deployment-pack.md)  
3. [`core/unified-deployment-and-security.md`](core/unified-deployment-and-security.md)  
4. Other files under `policies/`  
5. [`core/runtime/agent/`](core/runtime/agent/BOOTSTRAP.md) workspace pack  
6. Generated markdown / `operations/` state  

---

## Pairing: standards ↔ role-prompts

| Standards (policy) | Role prompt |
|--------------------|-------------|
| [`core/governance/standards/canonical-ai-agent-security-policy.md`](core/governance/standards/canonical-ai-agent-security-policy.md) | [`core/security-prompts.md`](core/security-prompts.md) |
| [`core/governance/standards/org-mapper-hr-policy.md`](core/governance/standards/org-mapper-hr-policy.md) | [`core/governance/role-prompts/org-mapper-hr-controller.md`](core/governance/role-prompts/org-mapper-hr-controller.md) |
| [`core/governance/standards/functional-director-policy-template.md`](core/governance/standards/functional-director-policy-template.md) | [`core/governance/role-prompts/functional-director-template.md`](core/governance/role-prompts/functional-director-template.md) |
| [`core/governance/standards/project-lead-policy-template.md`](core/governance/standards/project-lead-policy-template.md) | [`core/governance/role-prompts/project-lead-template.md`](core/governance/role-prompts/project-lead-template.md) |
| [`core/governance/standards/supervisor-policy-template.md`](core/governance/standards/supervisor-policy-template.md) | [`core/governance/role-prompts/supervisor-template.md`](core/governance/role-prompts/supervisor-template.md) |
| [`core/governance/standards/worker-specialist-policy-template.md`](core/governance/standards/worker-specialist-policy-template.md) | [`core/governance/role-prompts/worker-specialist-template.md`](core/governance/role-prompts/worker-specialist-template.md) |
| [`core/governance/standards/board-of-directors-review-policy.md`](core/governance/standards/board-of-directors-review-policy.md) | [`core/governance/role-prompts/board-of-directors-review.md`](core/governance/role-prompts/board-of-directors-review.md) |
| [`core/governance/standards/task-state-and-evidence-policy.md`](core/governance/standards/task-state-and-evidence-policy.md) | [`core/governance/role-prompts/task-state-evidence-enforcer.md`](core/governance/role-prompts/task-state-evidence-enforcer.md) |
| [`core/governance/standards/channel-architecture-policy.md`](core/governance/standards/channel-architecture-policy.md) | [`core/governance/role-prompts/future-channel-architecture-planner.md`](core/governance/role-prompts/future-channel-architecture-planner.md) |
| [`core/governance/standards/client-deployment-policy.md`](core/governance/standards/client-deployment-policy.md) | [`core/governance/role-prompts/client-intake-deployment-template.md`](core/governance/role-prompts/client-intake-deployment-template.md) |
| [`core/governance/standards/agent-lifecycle-org-hygiene-policy.md`](core/governance/standards/agent-lifecycle-org-hygiene-policy.md) | [`core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md`](core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md) |
| [`core/governance/standards/agentic-company-template.md`](core/governance/standards/agentic-company-template.md) | [`core/governance/role-prompts/markdown-playbook-generator.md`](core/governance/role-prompts/markdown-playbook-generator.md) · [`core/governance/role-prompts/minimal-default-deployment-order.md`](core/governance/role-prompts/minimal-default-deployment-order.md) |

---

## File index

All tracked markdown paths: [`INDEX.md`](INDEX.md).

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/pipeline-runbook.md](core/pipeline-runbook.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
