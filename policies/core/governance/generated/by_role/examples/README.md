<!-- policy-read-order-nav:top -->
> **Governance read order** — step 57 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../../../README.md)).
> **Before this file:** read [core/governance/generated/by_role/_TEMPLATE/README.md](../_TEMPLATE/README.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# By-role examples

This directory holds optional example artifacts for role workspaces under `by_role/`.

Keep examples non-sensitive and clearly labeled as reference material, not canonical policy.
# Example role slugs (non-binding)

These names illustrate how to label `by_role/<slug>/` folders. Replace with your org’s real roles.

| Slug | Example focus |
|------|----------------|
| `product_lead` | Backlog, roadmap alignment, stakeholder comms |
| `engineering_supervisor` | Code review gates, release risk, technical debt registers |
| `pipeline_specialist` | Data/ML/CI pipelines, reliability, runbooks |

Create real folders with `policies/core/scripts/materialize_role_workspace.py`.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/generated/playbooks/slack-department-project-task-routing.md](../../playbooks/slack-department-project-task-routing.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
