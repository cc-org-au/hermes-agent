# Org agent proposal and escalation (policy)

## Who may propose

- Any agent may **recommend** a new role or the retirement of a redundant role by **escalating upward** with written rationale, scope, tool/channel needs, and overlap analysis.

## Escalation path

1. **Worker / specialist** → **supervisor** (or project lead for project-scoped roles).
2. **Supervisor / project lead** → **functional director** for the affected lane (product, engineering, operations, IT/security).
3. **Directors** → **org / HR controller** (`ag-org-hr` profile and `org-mapper-hr-controller` prompt) for headcount / RACI / redundancy checks.
4. **HR / org** → **chief orchestrator** with a **single consolidated packet**: approvals at each prior level, dissenting views, and a **binary recommendation** (proceed / do not proceed).

## Chief decision

- The **chief** accepts or rejects implementation. **Unanimous director + HR sign-off** is required before the chief treats a proposal as **ready to implement**.
- On **accept**: update `scripts/core/org_agent_profiles_manifest.yaml`, run `scripts/core/bootstrap_org_agent_profiles.py`, update `ORG_CHART.md` / registers as your org requires, and document new `hermes_profile` names for `delegate_task`.
- On **reject**: record rationale in workspace governance notes; do not add profiles or gateway bots without a new proposal cycle.

## Automatic HR consultation (runtime)

When enabled in `workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml` under **`hr_consultation`**, the **chief** (parent agent with `delegate_task`, not subagents) automatically delegates once per matching user turn to **`hermes_profile`** (default `ag-org-hr`) and **appends** the subagent summary to the same turn’s user message. Tune **`trigger_keywords`** for your org. See `agent/hr_consultation.py` and the example block in `scripts/templates/hermes_token_governance.runtime.example.yaml`.

## Non-goals

- Hermes does not auto-create profiles from chat alone; **human operator** or chief-directed tooling runs the bootstrap script.
- Subagents cannot call `delegate_task`; only the **parent** chief (or another non-child context with delegation enabled) assigns `hermes_profile` delegation.
