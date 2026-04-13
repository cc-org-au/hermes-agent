# Workspace and Runtime Map

## Purpose

Define where policy/runtime files live and how materialized workspace paths are interpreted.

## Durable Map

- Runtime entry context is anchored by `../references/anchors/.hermes.md`.
- Workspace operating files include `../references/anchors/bootstrap.md`, `../references/anchors/agents.md`, and this memory tree.
- `workspace/memory/runtime/operations/` remains the registry and operations payload area after materialization.
- Canonical policy source remains repository policy files; workspace copies are applied runtime artifacts.

## Runtime Scripts

- `memory/runtime/tasks/scripts/activate-runtime-memory.sh`
- `memory/runtime/tasks/scripts/deploy-operations-artifacts.sh`
- `memory/runtime/tasks/scripts/restart-governance-runtime.sh`

## Source Canon

- `../references/anchors/.hermes.md`
- `../references/anchors/workspace.md`
- `../../README.md`
- `../references/anchors/bootstrap.md`

## Read Next

- `../../runtime/tasks/procedures/session-and-bootstrap.md`
- `../../runtime/tasks/procedures/generated-artifacts-and-deployment.md`
- `../references/ROUTING_DOCS.md` — **entry point** listing all `references/routing/*.md` repo paths (use git checkout + `git pull`)
- `../references/routing/README.md` — routing/cost reference (optional rsync into `${HERMES_HOME}/workspace/memory/...`)

## Memory Network

- `../references/index/memory-network.md`
