# Security sub-agents register (REM-006)

> **Status:** Registry instantiated in workspace. These are **governance roles**, not separate Hermes processes, until you add delegate profiles / runbooks.
> Canonical phase list: `policies/core/unified-deployment-and-security.md` (Phase 4) and `policies/core/agentic-company-deployment-pack.md` (Phase 3).

**AG-ID numbering:** `AG-005` is reserved for the **Project Lead** (`agentic-company`). Nine security foundation roles use `AG-004` and `AG-006`–`AG-013`.

| AG-ID | Role | Unified doc § | Policy / prompt anchor |
|-------|------|---------------|-------------------------|
| AG-004 | Startup Preflight Security Agent | Phase 4 #4 | `policies/core/governance/standards/canonical-ai-agent-security-policy.md` + Session 5 security prompts |
| AG-006 | Continuous Drift and Monitoring Agent | Phase 4 #5 | same (drift / monitoring posture) |
| AG-007 | Filesystem and Execution Security Agent | Phase 4 #6 | same |
| AG-008 | Browser and Web Security Agent | Phase 4 #7 | same |
| AG-009 | Integration and Identity Security Agent | Phase 4 #8 | same + messaging allowlists / `gateway/run.py` |
| AG-010 | Prompt Injection and Memory Defense Agent | Phase 4 #9 | same |
| AG-011 | Outbound Exfiltration Guard Agent | Phase 4 #10 | same |
| AG-012 | Patch, Dependency, and Supply-Chain Security Agent | Phase 4 #11 | same |
| AG-013 | Incident Response Agent | Phase 4 #12 | `INCIDENT_REGISTER.md`, `SECURITY_ALERT_REGISTER.md` |

## Instantiation checklist (operator)

1. For each role, create a **short role card** under `workspace/policies/core/governance/generated/by_role/` or your org’s equivalent when materialized from repo policies.
2. Map tool/channel constraints via **profile config**, env (e.g. allowlists), and `hermes_token_governance.runtime.yaml` per `agent/token_governance_runtime.py` (tier / blocklist / caps — not arbitrary per-role tool matrices in core).
3. Use **Chief Orchestrator delegation** or dedicated sessions with the Session *N* activation prompts; do not spawn nine long-lived OS processes unless you have capacity to monitor them.

## Unfinished (expected)

- No dedicated per-role markdown prompts ship in-repo for rows above (use canonical security standard + chief directive).
- Runtime **automation** (scheduled drift jobs, preflight hooks) is operator-defined.
