<!-- policy-read-order-nav:top -->
> **Governance read order** — step 51 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../README.md)).
> **Before this file:** read [core/governance/role-prompts/minimal-default-deployment-order.md](role-prompts/minimal-default-deployment-order.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Artifacts, generation, and archival memory

This document defines how the **agentic company** pipeline produces **runtime files** and **memory** outside the canonical policy text. It applies to every deployment that uses this `policies/` tree.

---

## 1. Two runtime zones

| Zone | Path (default) | Purpose |
|------|----------------|---------|
| **Policy-side generation** | `policies/core/governance/generated/` in source control; runtime copy under `AGENT_HOME/workspace/policies/core/governance/generated/` when editable | New markdown **derived from** policy work (playbooks, extensions, scoped directives). Indexed; visible to orchestrator and leads. |
| **Operational truth** | `AGENT_HOME/workspace/operations/` | Cross-project **registers**, audits, and **per-project** folders. Not a substitute for canonical policies. |

Keep canonical policy sources under `policies/` (except `generated/`) auditable and small. **Numbered domain policies** live in `policies/core/governance/standards/`. Put volume and churn in `AGENT_HOME/workspace/operations/` or `AGENT_HOME/workspace/policies/core/governance/generated/`.

### Runtime placement model (mandatory)

- `AGENT_HOME` is the runtime agent home root (commonly `~/.agent`).
- Canonical policy files used at runtime should be staged under `AGENT_HOME/policies/` (or equivalent policy root under `AGENT_HOME`) so the agent can read them without treating them as routine editable workspace files.
- Workspace-editable runtime files live under `AGENT_HOME/workspace/`.
- Operational registers and project archival memory always live under `AGENT_HOME/workspace/operations/`.
- Only policy files expected to change during routine operation should be in `AGENT_HOME/workspace/policies/` (for example generated markdown and approved local runtime working copies).

---

## 2. `operations/` layout (mandatory shape)

At `AGENT_HOME/workspace/`:

```text
operations/
  README.md                    # operator index; list active projects
  ORG_REGISTRY.md              # from unified runbook
  ORG_CHART.md
  AGENT_LIFECYCLE_REGISTER.md
  TASK_STATE_STANDARD.md
  BOARD_REVIEW_REGISTER.md
  CHANNEL_ARCHITECTURE.md
  SECURITY_ALERT_REGISTER.md
  SECURITY_AUDIT_REPORT.md
  SECURITY_REMEDIATION_QUEUE.md
  INCIDENT_REGISTER.md
  projects/
    <project_slug>/
      README.md                # project charter, visibility, lead
      memory/
        active/                # short-lived working notes (optional)
        archival/              # dated append-only archival files (mandatory use)
      artifacts/               # deliverables, exports, non-memory outputs
      generated/               # project-scoped markdown not promoted to policies/core/governance/generated/
```

**Archival rule:** Any agent with a project affiliation **must** write to `AGENT_HOME/workspace/operations/projects/<slug>/memory/archival/` continuously: dated filenames (`YYYY-MM-DD_topic.md` or sequential `0001_topic.md`), append-style entries for decisions, evidence pointers (not secrets), blockers, and handoffs. **Active recall:** orchestrators and project leads **must** consult recent archival files when resuming work or answering status questions.

Orchestrator `agent/MEMORY.md` holds **pointers** to archives, not a duplicate of full project history.

---

## 3. `policies/core/governance/generated/` layout

On-demand markdown **approved by policy** (orchestrator, project lead, or security role per runbook) is stored here so it remains part of the **same brain** and discoverable.

```text
policies/core/governance/generated/
  README.md                    # index: table of paths, owner role, date, upstream policy anchor
  playbooks/                   # procedural bundles
  extensions/                  # scoped addenda to roles or channels
  audits/                      # non-authoritative audit summaries (authoritative registers stay in operations/)
  experiments/                 # time-boxed; must declare expiry or promotion path
  by_role/                     # durable workspace per company role (see by_role/README.md)
    _TEMPLATE/                 # copy starter for new roles
    <role_slug>/               # e.g. product_lead — standards/, playbooks/, decisions/, scratch/
```

**Wiring rule:** Every new file under `policies/core/governance/generated/` must be listed in `policies/core/governance/generated/README.md` with: **title, path, owning role, date, related canonical policy/runbook section**. In runtime environments, keep the editable generated tree under `AGENT_HOME/workspace/policies/core/governance/generated/` and keep that index updated. Project-scoped generated docs that should **not** be shared company-wide stay under `AGENT_HOME/workspace/operations/projects/<slug>/generated/`.

---

## 4. On-demand markdown generation

Agents **may** create new markdown files when needed to satisfy a governed goal or project scope, provided:

1. The creator’s role is allowed to produce that artifact class (canonical pack + runbook).  
2. The file lands in `policies/core/governance/generated/` (or runtime editable mirror under `AGENT_HOME/workspace/policies/core/governance/generated/`) **or** `AGENT_HOME/workspace/operations/projects/<slug>/generated/` per scope.  
3. The index (`policies/core/governance/generated/README.md` or project `README.md`) is updated in the same change window.  
4. No secrets, credentials, or unredacted PII.  
5. Naming is consistent and sortable (prefix dates or serials).

Forbidden: silent drops of policy-adjacent files into random folders without index updates.

---

## 5. Deployment sync (agent pack)

When policies or prompts change materially, the **workspace agent pack** (`policies/core/runtime/agent/*.md`) must stay aligned:

- `AGENTS.md` and `BOOTSTRAP.md` reference this document and `policies/README.md`.  
- `MEMORY.md` reflects active vs archival split.  
- `ORCHESTRATOR.md` references project paths and isolation.  
- `SECURITY.md` references canonical security policy and runbook paths.

Deployment agents **must** reconcile those files after policy edits so runtime agents inherit constraints without drifting copies of the full canonical pack.

---

## 6. Security

- Treat `AGENT_HOME/workspace/operations/` as sensitive operational data; restrict filesystem ACLs in real deployments.  
- Archival files contain **operational memory**, not credentials.  
- Generated markdown is still subject to untrusted-content rules in the security policy.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/generated/README.md](generated/README.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
