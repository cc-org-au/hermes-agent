# Project Leads register (REM-009)

| AG-ID | Project slug | Status | Policy | Prompt |
|-------|--------------|--------|--------|--------|
| **AG-005** | `agentic-company` | **ACTIVE (registry)** | `policies/core/governance/standards/project-lead-policy-template.md` | `policies/core/governance/role-prompts/project-lead-template.md` |

## Project brief (agentic-company)

- **Scope:** Operate the in-repo **agentic company** deployment: policies under `HERMES_HOME/policies`, workspace under `HERMES_HOME/workspace`, Hermes gateway + chief-orchestrator profile, remediation items (REM-*), and alignment with `policies/core/deployment-handoff.md`.
- **Success:** Governance pack materialized, token governance runtime active, messaging allowlists set, watchdog healthy, no drift vs canonical `policies/` without recorded exception.
- **Escalation:** Chief Orchestrator for cross-project strategy; IT/Security Director (when activated) for trust-boundary changes.

## Paths

- Project workspace folder: `operations/projects/agentic-company/` (see `README.md` there).

## Unfinished (expected)

- **Hermes delegate_tool** sub-agent profile for AG-005 is optional — not created automatically.
- Human operator still owns irreversible production changes (SSH, firewall, secrets rotation).
