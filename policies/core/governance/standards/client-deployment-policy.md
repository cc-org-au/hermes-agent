<!-- policy-read-order-nav:top -->
> **Governance read order** — step 47 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/role-prompts/future-channel-architecture-planner.md](../role-prompts/future-channel-architecture-planner.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# CLIENT_DEPLOYMENT_POLICY.md

## Activation prompt (role reminder)

When enforcing this policy, load the associated prompt(s) **in the same session** so operational role constraints and tone stay aligned with governance:

- `../role-prompts/client-intake-deployment-template.md`

---

## Purpose

This policy governs how the architecture is deployed for a new client company.

No client deployment may begin without intake and tailoring.

---

## Required Intake Questions

1. What does your company do?
2. What are your top 3 objectives over the next 90 days?
3. What are your biggest bottlenecks right now?
4. What tools and systems do you already use?
5. What work should AI fully own, partially assist, or avoid entirely?
6. What approvals, constraints, legal boundaries, compliance requirements, or risk boundaries must the agents respect?
7. What outputs matter most to the business?

---

## Required Post-Intake Actions

After collecting client responses, the deployment agent must:
- recommend a lean department structure
- recommend which roles to instantiate immediately
- recommend which roles to keep dormant until justified
- define success metrics
- define escalation rules
- define memory rules
- define reporting cadence
- generate the client-specific markdown operating playbook

---

## Hard Rules

1. Do not deploy a bloated structure.
2. Start with the smallest structure that can credibly deliver outcomes.
3. Enable only the departments that map to real workload.
4. Tailor the hierarchy, cadence, rules, and metrics to the client’s actual context.
5. Preserve memory efficiency, role clarity, and auditability.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/client-intake-deployment-template.md](../role-prompts/client-intake-deployment-template.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
