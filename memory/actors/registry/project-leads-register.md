# Project Leads register (REM-009)

| AG-ID | Project slug | Status | Policy | Prompt |
|-------|--------------|--------|--------|--------|
| **AG-005** | `agentic-company` | **ACTIVE (registry)** | `workspace/memory/governance/source/standards/project-lead-policy-template.md` | `workspace/memory/governance/source/role-prompts/project-lead-template.md` — Hermes profile **`project-lead-agentic-company`** (manifest bootstrap) |

## Project brief (agentic-company)

- **Scope:** Operate the in-repo **agentic company** deployment: policies under `HERMES_HOME/policies`, workspace under `HERMES_HOME/workspace`, Hermes gateway + chief-orchestrator profile, remediation items (REM-*), and alignment with `policies/core/deployment-handoff.md`.
- **Success:** Governance pack materialized, token governance runtime active, messaging allowlists set, watchdog healthy, no drift vs canonical `policies/` without recorded exception.
- **Escalation:** Chief Orchestrator for cross-project strategy; IT/Security Director (when activated) for trust-boundary changes.

## Paths

- Project workspace folder: `memory/knowledge/projects/agentic-company/` (see `README.md` there).

## Delegation

- Bootstrap profile: `./venv/bin/python scripts/bootstrap_org_agent_profiles.py` → **`project-lead-agentic-company`**. Chief calls `delegate_task(..., hermes_profile="ag-pl-agentic-company")` for project-lane work.

## Operator-owned

- Irreversible production changes (SSH, firewall, secrets rotation) remain human-owned unless policy explicitly delegates.
