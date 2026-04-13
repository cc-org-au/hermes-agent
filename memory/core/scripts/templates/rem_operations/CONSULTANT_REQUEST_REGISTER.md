# Consultant request register (premium model workflow)

> **Template for requests:** `operations/CONSULTANT_REQUEST_TEMPLATE.md` (materialized from repo templates).  
> **Purpose:** Operational log for **premium / consultant model** use: justification, approval, and audit.

## Workflow

1. **Requester** opens a row below (draft): problem statement, why default tier is insufficient, estimated tokens/cost, time box.
2. **Supervisor or director** (as applicable) endorses or rejects.
3. **Chief** approves execution; operator may set **`HERMES_GOVERNANCE_ALLOW_PREMIUM=1`** for a bounded window **or** adjust `hermes_token_governance.runtime.yaml` per policy.
4. **Close** the row with outcome and link to artefacts (session id, export path).

## Open requests

| ID | Date opened | Requester | Model / tier asked | Business justification | Approvals (supervisor → chief) | Status |
|----|-------------|-------------|--------------------|-------------------------|----------------------------------|--------|
| | | | | | | draft / approved / rejected / completed |

## Completed

| ID | Closed | Outcome | Notes |
|----|--------|---------|-------|
| | | | |

## Policy cross-links

- `token-model-tool-and-channel-governance-policy.md`
- `workspace/memory/runtime/operations/hermes_token_governance.runtime.yaml`
- `agent/consultant_routing.py` (governance activation heuristics)
