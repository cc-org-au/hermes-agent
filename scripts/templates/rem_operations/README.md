# Workspace operations (`WORKSPACE/operations/`)

This directory holds **runtime registers** for the agentic-company / chief-orchestrator deployment. Canonical **policy** lives under `POLICY_ROOT/`; this tree is **operational state**.

## Index (maintain as files are added)

| File | Purpose |
|------|---------|
| `ORG_REGISTRY.md` | Org chart / agent IDs |
| `SECURITY_SUBAGENTS_REGISTER.md` | AG-004, AG-006–AG-013 + `ag-sec-*` profiles |
| `SECURITY_ALERT_REGISTER.md` | Session 11 warnings (W001–W004) |
| `CHANNEL_ARCHITECTURE.md` | Allowlist IDs + env vars (Session 10) |
| `MODEL_ROUTING_REGISTRY.md` | Tier / routing intent |
| `hermes_token_governance.runtime.yaml` | Enforced caps (`max_agent_turns`, tiers) — loaded by `agent/token_governance_runtime.py` |
| `SKILL_INVENTORY_REGISTER.md` | W004 skill source/version/permissions |
| `CONSULTANT_REQUEST_REGISTER.md` | Premium model approvals |
| `BOARD_REVIEW_REGISTER.md` | Board decisions log |
| `MEMORY_INTEGRATION_OVERRIDE.md` | Memory vs registers strategy |
| `CHIEF_ORCHESTRATION_PLAYBOOK.md` | Delegation + messaging |
| `ORG_AGENT_ESCALATION_PLAYBOOK.md` | New/retired agent proposals |
| `GOVERNANCE_CHANGELOG.md` | (optional) dated applied changes |
| `projects/agentic-company/README.md` | AG-005 project hub |

## Hygiene (ORG_HYGIENE_RULES §6–7)

- **Weekly (light):** scan `SECURITY_ALERT_REGISTER` for open rows; confirm gateway `watchdog-check` healthy.
- **Monthly:** `CHANNEL_ARCHITECTURE.md` vs live integrations; `SKILL_INVENTORY_REGISTER.md` row accuracy.
- **Quarterly:** `BOARD_REVIEW_REGISTER.md` entry or explicit “no review required”; token governance `tier_models` sanity vs OpenRouter catalog.

## Sync from repo templates

From repo root, with `HERMES_HOME` set to the chief profile:

```bash
export HERMES_HOME="$HOME/.hermes/profiles/chief-orchestrator"
REM_OPERATIONS_FORCE=1 ./scripts/materialize_rem_operations.sh
```

`REM_OPERATIONS_FORCE=1` **overwrites** listed templates (use after `git pull` to refresh registers).

## Governance enforcement note

- There is **no** `agent/governance.py` in core. **Model / turn caps** come from **`agent/token_governance_runtime.py`** reading `hermes_token_governance.runtime.yaml` (`max_agent_turns`). Logs: `Token governance: baseline …` and per-turn tier lines (gateway + CLI).
- **HR / org auto-consultation:** optional `hr_consultation` block in the same YAML — chief delegates to `ag-org-hr` when keywords match; see `agent/hr_consultation.py`.
