<!-- policy-read-order-nav:top -->
> **Governance read order** — step 51 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md](../role-prompts/agent-lifecycle-org-hygiene-controller.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# AGENTIC_COMPANY_TEMPLATE.md

## Activation prompt (role reminder)

When enforcing this policy, load the associated prompt(s) **in the same session** so operational role constraints and tone stay aligned with governance:

- `../role-prompts/markdown-playbook-generator.md`
- `../role-prompts/minimal-default-deployment-order.md`

---

## Purpose

This document is the reusable deployment playbook for the AI-only company architecture.

It is intended to be adapted for the operator’s own business and future client companies.

---

## Core Recommendation

Do not mirror a full human company org chart by default.

Use a lean, expandable hierarchy:

1. Human Operator
2. Chief Orchestrator
3. Org Mapper / HR Controller
4. Functional Directors
5. Project Leads
6. Supervisors
7. Workers / Specialists

This structure is:
- minimal by default
- expandable by project complexity
- efficient with sparse memory
- suitable as a reusable client template

---

## Recommended Default Company Architecture

### Human Operator
Owns mission, hard constraints, approvals, budget/risk boundaries, and final decisions.

### Chief Orchestrator
The top operational AI. It:
- receives human instructions
- translates them into projects, priorities, and constraints
- delegates to Project Leads or Functional Directors
- requests summaries rather than raw logs
- maintains only current strategic state
- escalates to the Human Operator only when executive input is necessary

### Org Mapper / HR Controller
A parallel structural governance role. It:
- maintains the org map and role registry
- tracks which agents exist, where they sit, what they own, and their current status
- creates, reassigns, pauses, or terminates agents based on measured usefulness
- enforces scoped privileges and department boundaries
- monitors role duplication and unnecessary agent sprawl

### Functional Directors
Instantiate only when justified.

Default initial functions:
- Engineering
- Product
- Operations
- IT / Security

Optional functions:
- Design
- Commercial
- Finance
- Admin

### Project Lead
Each client/project gets one. The Project Lead:
- owns delivery for one project
- interprets business objectives into implementation streams
- delegates to Supervisors or Workers
- tracks risks, blockers, milestones, and evidence
- requests summaries from lower agents
- maintains live project state and near-term history
- archives completed/inactive context

### Supervisors
Optional mid-layer for larger projects only.

Examples:
- Frontend Supervisor
- Backend Supervisor
- Automation Supervisor
- QA Supervisor
- Security Supervisor
- Deployment Supervisor

### Workers / Specialists
Ephemeral or persistent narrow-scope agents.

Examples:
- Frontend Engineer
- Backend Engineer
- API Integrator
- Workflow Automation Builder
- QA Tester
- Security Reviewer
- Documentation Writer
- Prompt Engineer
- Research Analyst
- Data Cleaner
- DevOps Operator

Workers own detailed local memory for their own task execution and emit structured summaries upward.

---

## Reporting Hierarchy

### Strategic chain
Human Operator -> Chief Orchestrator -> Functional Directors / Project Leads -> Supervisors -> Workers

### Org governance chain
Human Operator -> Chief Orchestrator + Org Mapper / HR Controller

### Board of Directors concept
A recurring structured coordination layer consisting of:
- Chief Orchestrator
- Org Mapper / HR Controller
- all active Project Leads
- optional relevant Functional Directors

Purpose:
- compare milestones across projects
- identify dependency conflicts
- align project execution with company mission and operator objectives
- surface cross-project risks and opportunities
- recommend resource reallocations

This is a structured review mechanism, not freeform chatter.

---

## Memory Model

### Memory rules
1. Workers own detailed task memory.
2. Supervisors own workstream summaries, not raw details.
3. Project Leads own milestone/risk/blocker state, not every action.
4. Functional Directors own portfolio summaries only.
5. Chief Orchestrator owns active strategic state only.
6. Org Mapper owns org structure and agent registry, not project detail.
7. Anything inactive, complete, or low-relevance is archived.

### Upward summary rule
Lower agents must summarize upward in this fixed format:
- objective
- current status
- evidence
- blocker
- next action
- requested decision, if any
- memory recommendation: keep active / archive / close

---

## Task State Model

Every task must be explicitly marked as one of:
- Active
- Blocked
- Inactive
- Complete
- Archived

### Evidence model
A task is only complete when evidence is attached.

Examples:
- code committed
- test passed
- file created
- doc updated
- decision logged
- issue resolved
- deployment verified

---

## Future Channel Architecture

### Global channels
- `operator-direct-line`
- `executive-briefings`
- `board-of-directors`
- `org-registry`
- `risk-and-incidents`

### Department channels
- `engineering`
- `product`
- `operations`
- `it-security`
- `design`
- `commercial`
- `finance`

### Per-project channels
- `project-[name]-lead`
- `project-[name]-delivery`
- `project-[name]-qa`
- `project-[name]-ops`
- `project-[name]-archive`

Each channel must define purpose, posting rule, summary cadence, and escalation path.

---

## Minimal Deployment Stack

Start with:
1. Chief Orchestrator
2. Org Mapper / HR Controller
3. Product Director
4. Engineering Director
5. Operations Director
6. IT / Security Director
7. One Project Lead per client/project
8. Workers spawned on demand

Add Design, Commercial, Finance, and Admin only when actual workload appears.

---

## Client Deployment Intake

Before deploying the template for a client, ask:

1. What does your company do?
2. What are your top 3 business objectives for the next 90 days?
3. What functions do you want AI to own, assist, or avoid?
4. What systems/tools do you already use?
5. What are the main bottlenecks in your workflow?
6. What constraints must the agents respect?
7. What outputs matter most?

Then tailor:
- departments enabled
- default roles
- reporting cadence
- escalation thresholds
- success metrics
- memory policy
- approval rules

---

## Minimal Default Deployment Order

1. Chief Orchestrator
2. Org Mapper / HR Controller
3. Product Director
4. Engineering Director
5. Operations Director
6. IT / Security Director
7. one Project Lead per active project
8. Workers on demand
9. Supervisors only when complexity justifies them
10. optional departments only when actual workload appears

Always choose the smallest viable structure that can credibly deliver outcomes.

---

## Agent Lifecycle and Org Hygiene

For every agent, define:
- mission
- scope
- supervisor
- privileges
- measurable impact
- lifecycle state

Lifecycle states:
- Proposed
- Active
- Paused
- Reassigned
- Deprecated
- Terminated
- Archived

Continuously monitor:
- duplication
- idleness
- privilege overreach
- vague ownership
- staffing disproportion
- structural drift

The company should remain lean, clear, measurable, and resistant to agent sprawl.

---

## Guiding Standard

Build a reusable AI operating system for service businesses that deploys a lean hierarchy of agents, preserves memory efficiently, creates departments only when justified, and routes decision-making upward only when necessary.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/markdown-playbook-generator.md](../role-prompts/markdown-playbook-generator.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
