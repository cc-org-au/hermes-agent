# Artifacts, Generated, and Template Integration

Consolidated rules for runtime zones, generated outputs, and template use.

## Two Runtime Zones

Policy zone (canonical source):

- `workspace/memory/governance/source/*`

Runtime zone (operational truth for instantiated work):

- `HERMES_HOME/workspace/memory/runtime/operations/*`

Rules:

- Keep canonical standards in policy zone.
- Keep live registers and current operations state in runtime zone.
- Sync policy updates to runtime surfaces through controlled activation workflows.

Required runtime register surfaces include:

- `ORG_REGISTRY.md`
- `TASK_STATE_STANDARD.md`
- `CHANNEL_ARCHITECTURE.md`
- security register set (alerts, remediation queue, audit report)
- board and incident review registers

## Generated and Template Contract

Generated outputs are integrated into runtime templates under:

- `../../governance/protocols/governance-generated/`

Template and generated usage:

- Use generated templates for repeatable role workspaces and playbooks.
- Do not treat examples as canonical policy.
- Add date/path/owner/anchor metadata for generated outputs.

Required generated index columns:

- Date (UTC)
- Path
- Title/Purpose
- Owning Role
- Anchor (policy or runbook section)

## Archival and Evidence

Preserve:

- append-only evidence logs for major decisions
- structured archival naming
- no secrets in archival markdown

Memory behavior:

- keep long historical traces in `../../runtime/logs/`
- keep active operational constraints in `../../runtime/state/`

Deployment sync targets for runtime policy visibility:

- `../../knowledge/references/anchors/agents.md`
- `../../knowledge/references/anchors/bootstrap.md`
- `../../knowledge/concepts/foundation-memory-contract.md`
- `../../governance/*`

## Read Next

- `../policy/enforcement-and-standards.md`
- `../prompt/role-prompt-injection-rules.md`
- `governance-generated/README.md`
