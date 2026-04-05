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

The numbering maps to **`POLICY_ROOT/core/governance/standards/agent-lifecycle-org-hygiene-policy.md`**: **§6-style** ≈ *Org Hygiene Requirements* (duplication, drift, privilege, ownership); **§7-style** ≈ *Required Outputs* (lifecycle / duplication / privilege reports). This `operations/` tree is where **evidence** for those reviews accumulates.

| Cadence | Actions |
|---------|---------|
| **Weekly** | Scan `SECURITY_ALERT_REGISTER.md` for non-COMPLETE rows; `hermes gateway watchdog-check` healthy; glance `gateway_state.json` for platform errors. |
| **Monthly** | Re-run `scripts/render_workspace_registers_from_env.py` after messaging `.env` changes; spot-check `CHANNEL_ARCHITECTURE.md` vs Slack/Telegram/Discord/WhatsApp invites; audit `SKILL_INVENTORY_REGISTER.md` vs `skills/*/SKILL.md` permissions. |
| **Quarterly** | `BOARD_REVIEW_REGISTER.md` real session **or** explicit “no review required” row; `CONSULTANT_REQUEST_REGISTER.md` backlog review; `tier_models` vs OpenRouter catalog; org profile list vs `org_agent_profiles_manifest.yaml`. |

## Sync from repo templates

From repo root, with `HERMES_HOME` set to the chief profile:

```bash
export HERMES_HOME="$HOME/.hermes/profiles/chief-orchestrator"
REM_OPERATIONS_FORCE=1 ./scripts/materialize_rem_operations.sh
```

`REM_OPERATIONS_FORCE=1` **overwrites** listed templates (use after `git pull` to refresh registers).

### Live IDs + skill inventory (W003 / W004)

After changing messaging **`.env`**, regenerate operational tables from the active profile:

```bash
export HERMES_HOME="$HOME/.hermes/profiles/chief-orchestrator"
./venv/bin/python scripts/render_workspace_registers_from_env.py
```

Then restart the gateway if you changed allowlists or tokens.

## Governance enforcement note

- There is **no** `agent/governance.py` in core. **Model / turn caps** come from **`agent/token_governance_runtime.py`** reading `hermes_token_governance.runtime.yaml` (`max_agent_turns`). Logs: `Token governance: baseline …` and per-turn tier lines (gateway + CLI).
- **HR / org auto-consultation:** optional `hr_consultation` block in the same YAML — chief delegates to `ag-org-hr` when keywords match; see `agent/hr_consultation.py`.
