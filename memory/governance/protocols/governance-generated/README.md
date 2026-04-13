# Governance Generated Templates

This directory contains template-style governance artifacts integrated from `workspace/memory/governance/source/generated`.

## Files

- `slack-department-project-task-routing-template.md`

## By-Role Workspace Pattern

Use `by_role/<role_slug>/` semantics when materializing role-scoped generated work:

- one role folder per logical role instance
- stable top-level charter and links, volatile details in dated subfiles
- promote mature role norms into canonical standards via governance process
- include active project links to `memory/knowledge/projects/<slug>/`

Minimal folder shape:

```text
by_role/<role_slug>/
  README.md
  standards/
  playbooks/
  decisions/
  scratch/
```

Example non-binding role slugs:

- `product_lead`
- `engineering_supervisor`
- `pipeline_specialist`

## Usage Rules

- Treat these as reusable templates, not canonical policy.
- Preserve metadata for generated outputs (date, path, owner, anchor).
- Keep standards enforcement in `../../policy/enforcement-and-standards.md`.

## Read Next

- `../artifacts-template-protocol.md`
