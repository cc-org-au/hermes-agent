<!-- policy-read-order-nav:top -->
> **Governance read order** — step 53 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../../README.md)).
> **Before this file:** read [core/governance/generated/README.md](../README.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Generated output by role (scaling template)

Use this layout when a **named company role** (e.g. product lead, engineering supervisor, pipeline specialist) needs a **durable workspace** under `policies/core/governance/generated/` that can grow without flattening everything into one folder.

## Principles

1. **One role folder per logical role instance** — `by_role/<role_slug>/` (slug: `product_lead`, `eng_supervisor`, `pipeline_specialist`, etc.).  
2. **Stable spine, volatile detail** — keep long-lived indexes and standards at the top of the role tree; put day-to-day churn in dated or numbered subfolders.  
3. **Promote upward** — material that becomes company-wide policy belongs in [`../../governance/standards/`](../../standards/canonical-ai-agent-security-policy.md) or [`../../agentic-company-deployment-pack.md`](../../agentic-company-deployment-pack.md) through governance, not by silent edits here.  
4. **Cross-link** — each role folder has a `README.md` listing active projects and pointers to `operations/projects/<slug>/`.

## Folder shape (minimal)

```text
policies/core/governance/generated/by_role/<role_slug>/
  README.md           # charter, scope, active projects, links to policies/core/governance/standards/* and policies/core/governance/role-prompts/*
  standards/          # role-specific norms that are not yet canonical policy
  playbooks/          # repeatable procedures for this role
  decisions/          # ADR-style or dated decision logs (no secrets)
  scratch/            # optional; low-formality notes to be triaged
```

## Creating a new role workspace

Run:

```bash
python policies/core/scripts/materialize_role_workspace.py <role_slug> [--title "Human Title"]
```

See `_TEMPLATE/README.md` for a copy-paste starter.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/generated/by_role/_TEMPLATE/README.md](_TEMPLATE/README.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
