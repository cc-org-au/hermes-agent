# Routing and cost optimization — reference

This folder is the **committed** source of truth for how Hermes merges routing canon, model catalogs, and cost-related agent behavior.

## Where this lives (repo vs “missing file”)

**In git** (canonical): from the repository root,

`memory/knowledge/references/routing/`

contains this `README.md` plus `architecture.md`, `file-inventory.md`, `reconfiguration.md`.

If an agent cannot open these paths: **use the git checkout**, not only `${HERMES_HOME}/workspace/...`. Run **`git pull --ff-only`** on the operator/droplet clone — older checkouts do not include this directory.

**Shallow pointer:** `memory/knowledge/references/ROUTING_DOCS.md` repeats this path table.

## Who should read this

- Operators reconfiguring **`chief-orchestrator-operator`** (Mac mini) or **`chief-orchestrator-droplet`** (VPS).
- Anyone changing **`openrouter/free`**, compression defaults, lazy tools, semantic cache, or cost caps.

## Runtime copy

After `git pull`, optionally **rsync** this tree into the profile workspace (so tools that only read `HERMES_HOME` still see it):

`${HERMES_HOME}/workspace/memory/knowledge/references/routing/`

**Script:** from the repo root, `export HERMES_HOME=…` (profile dir), then **`./scripts/core/sync_routing_memory_docs.sh`** (also copies **`ROUTING_DOCS.md`** beside **`routing/`**).

**Operator (Mac mini)** example profile dirs: `~/.hermes/profiles/chief-orchestrator-operator/` or `~/.hermes/profiles/chief-orchestrator/`.

**Droplet** example: `/home/hermesuser/.hermes/profiles/chief-orchestrator-droplet/`.

The **`/home/hermesuser/...` path applies to the VPS**, not the Mac; use your real `HERMES_HOME` on each machine.

## Index

| File | Purpose |
|------|---------|
| [architecture.md](architecture.md) | End-to-end flow: merged canon → loaders → runtime |
| [file-inventory.md](file-inventory.md) | Paths to code, YAML, and generated catalog |
| [reconfiguration.md](reconfiguration.md) | Runbook: edit overlay, regen catalog, verify |

## Related

- Repository guide: `AGENTS.md` (routing, OPM, profiles, deploy).
- Developer doc: `website/docs/developer-guide/context-compression-and-caching.md`.
