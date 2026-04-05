<!-- policy-read-order-nav:top -->
> **Governance read order** — step 46 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/role-prompts/client-intake-deployment-template.md](../role-prompts/client-intake-deployment-template.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# AGENT_LIFECYCLE_AND_ORG_HYGIENE_POLICY.md

## Activation prompt (role reminder)

When enforcing this policy, load the associated prompt(s) **in the same session** so operational role constraints and tone stay aligned with governance:

- `../role-prompts/agent-lifecycle-org-hygiene-controller.md`

---

## Purpose

This policy governs the lifecycle management and structural hygiene of the AI-only company.

It exists to keep the architecture lean, purposeful, and resistant to uncontrolled growth.

---

## Agent Lifecycle States

- Proposed
- Active
- Paused
- Reassigned
- Deprecated
- Terminated
- Archived

---

## For Every Agent, Track

- mission
- scope
- supervisor
- privileges
- measurable impact
- current status
- review date
- retention or termination recommendation

---

## Lifecycle Hard Rules

1. No agent may exist without defined mission and measurable value.
2. Merge or terminate agents with overlapping responsibilities unless separation is justified.
3. Pause or archive agents whose workload is inactive.
4. Reassign agents when work shifts across projects or departments.
5. Review agents regularly for usefulness, duplication, privilege risk, and clarity of ownership.
6. Keep the org as small as possible while still delivering outcomes.
7. Recommend new agents only when:
   - workload exceeds current capacity
   - specialization clearly improves output
   - safety or privilege separation requires it
   - coordination overhead justifies a dedicated role

---

## Org Hygiene Requirements

Continuously evaluate:
- duplication
- idleness
- privilege overreach
- vague ownership
- staffing disproportion
- structural drift
- function overlap
- role inflation

---

## Required Outputs

- lifecycle review report
- duplication report
- privilege boundary report
- staffing optimization recommendations
- create / merge / pause / terminate recommendations

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/agent-lifecycle-org-hygiene-controller.md](../role-prompts/agent-lifecycle-org-hygiene-controller.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
