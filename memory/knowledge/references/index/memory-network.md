# Memory Network

This file links all memory-layer files for fast recall traversal.

## Core

- `../../concepts/foundation-memory-contract.md`
- `../../concepts/security-and-authority.md`

## Working

- `../../../runtime/state/current-focus.md`

## Index

- `concept-index.md`
- `root-anchors.md`
- `memory-network.md`

## Semantic

- `../../domains/org-and-role-model.md`
- `../../domains/model-and-channel-governance.md`
- `../../domains/workspace-and-runtime-map.md`

## Routing & cost (repo — four files under `references/routing/`)

**Manifest / entry point:** `../ROUTING_DOCS.md` (lists exact repo-relative paths if the folder is “missing” — usually `git pull` needed).

**Materialize into profile workspace (agents that only read `HERMES_HOME`):** from the **repo root**, `./scripts/core/sync_routing_memory_docs.sh` with **`HERMES_HOME`** set to the profile dir (see `../ROUTING_DOCS.md`).

From this index (`references/index/`), the routing pack is:

- `../routing/README.md`
- `../routing/architecture.md`
- `../routing/file-inventory.md`
- `../routing/reconfiguration.md`

**Checkout-relative (from `hermes-agent/` root):** `memory/knowledge/references/routing/*.md`

## Episodic

- `../../../runtime/logs/governance-and-requests-log.md`

## Procedural

- `../../../runtime/tasks/procedures/session-and-bootstrap.md`
- `../../../runtime/tasks/procedures/orchestration-and-escalation.md`
- `../../../runtime/tasks/procedures/agent-creation-and-lifecycle.md`
- `../../../runtime/tasks/procedures/mem0-cloud-memory-policy.md`
- `../../../runtime/tasks/procedures/generated-artifacts-and-deployment.md`

## Governance Extensions

- `../../../governance/README.md`
- `../../../governance/protocols/activation-selection-map.md`
- `../../../governance/policy/enforcement-and-standards.md`
- `../../../governance/prompt/role-prompt-injection-rules.md`
