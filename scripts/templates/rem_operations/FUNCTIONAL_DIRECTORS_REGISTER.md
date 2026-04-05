# Functional Directors register (REM-007)

> **REM-007 decision:** Directors remain **DORMANT** until workload justifies activation. This register records the four **default** director slots from `policies/core/unified-deployment-and-security.md` Phase 6.

| Role | Policy template | Prompt template | Status |
|------|-----------------|-----------------|--------|
| Product Director | `policies/core/governance/standards/functional-director-policy-template.md` (tailor title) | `policies/core/governance/role-prompts/functional-director-template.md` | **DORMANT** |
| Engineering Director | same | same | **DORMANT** |
| Operations Director | same | same | **DORMANT** |
| IT / Security Director | same | same | **DORMANT** |

## Activation criteria (operator)

Instantiate a director when **all** are true:

1. Multiple active projects need **function-wide** standards or portfolio summaries.
2. Chief Orchestrator is spending cycles on department-level coordination that should be delegated.
3. You can name a **single accountable** session/profile per director (no overlapping “shadow” directors).

## Unfinished (expected)

- No automatic promotion from DORMANT → ACTIVE; operator updates this file and `ORG_CHART.md` when activating.
- Hermes does not schedule director reviews unless you add cron / manual cadence.
