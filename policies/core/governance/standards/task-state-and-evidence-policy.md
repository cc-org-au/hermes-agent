<!-- policy-read-order-nav:top -->
> **Governance read order** — step 40 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/role-prompts/board-of-directors-review.md](../role-prompts/board-of-directors-review.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# TASK_STATE_AND_EVIDENCE_POLICY.md

## Activation prompt (role reminder)

When enforcing this policy, load the associated prompt(s) **in the same session** so operational role constraints and tone stay aligned with governance:

- `../role-prompts/task-state-evidence-enforcer.md`

---

## Purpose

This policy governs task state clarity and evidence-based completion across the entire architecture.

---

## Approved Task States

- Active
- Blocked
- Inactive
- Complete
- Archived

---

## Hard Rules

1. Every task must always have one explicit state.
2. No task may be marked Complete without evidence.
3. No Active task may lack a next action.
4. Every Blocked task must include the blocking dependency or missing decision.
5. Every Inactive task must include the reason for inactivity.
6. Every Archived task must include the reason for archival and a retrieval reference.
7. State changes must be tracked at the appropriate level and summarized upward concisely.
8. Higher levels should retain only the latest relevant task state, not full historical logs.

---

## Valid Evidence Examples

- code committed
- file created
- test passed
- workflow executed
- deployment verified
- document updated
- approval recorded
- issue resolved
- artifact delivered

---

## Standard State Update Format

- task
- prior state
- new state
- reason
- evidence
- next action
- archive recommendation, if applicable

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/task-state-evidence-enforcer.md](../role-prompts/task-state-evidence-enforcer.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
