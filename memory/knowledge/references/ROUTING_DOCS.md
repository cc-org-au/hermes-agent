# Routing & cost docs — entry point (read this to find the folder)

The four routing reference files live **in this repository** under:

**`memory/knowledge/references/routing/`** (from the `hermes-agent` checkout root)

| File (repo-relative) | Role |
|----------------------|------|
| `memory/knowledge/references/routing/README.md` | Index + who should read + sync rule |
| `memory/knowledge/references/routing/architecture.md` | Merged canon → loaders → runtime; `openrouter/free`; prompt caching |
| `memory/knowledge/references/routing/file-inventory.md` | Table of code/YAML/catalog paths |
| `memory/knowledge/references/routing/reconfiguration.md` | Runbook: overlays, pytest, droplet/operator, OPM/Gemini fix |

If these paths **404 or “not found”** on a host:

1. **`cd` to the Hermes git checkout** (e.g. `~/hermes-agent` on the Mac mini, `/home/hermesuser/hermes-agent` on the droplet).
2. Run **`git pull --ff-only`** — the folder is committed on `main`; an old clone will not have it.
3. List with: **`ls memory/knowledge/references/routing/`**

## Materialized copy under `HERMES_HOME` (optional)

Orchestrator agents may read **`${HERMES_HOME}/workspace/memory/knowledge/references/routing/`** after you **rsync** from the repo (same four files).

**On the machine that already has the checkout:** set **`HERMES_HOME`** to the active profile, then **`./scripts/core/sync_routing_memory_docs.sh`** — **rsync** from repo into **`${HERMES_HOME}/workspace/memory/...`**.

**From your workstation (no shell on operator/droplet):**
- **Mac mini:** **`./scripts/core/push_routing_memory_docs_operator.sh`** (uses **`hermes_cli/scripts/core/ssh_operator.sh`** + tarball over SSH).
- **Droplet:** **`./scripts/core/push_routing_memory_docs_droplet.sh`** (**scp** as admin, then **`droplet_run`** as **`hermesuser`** — do not pipe the tarball through **`droplet_run`**; **`sudo -S`** + **`ssh -tt`** will mis-handle stdin).

That path is **profile-local**, e.g.:

- **Operator (Mac mini):** `~/.hermes/profiles/chief-orchestrator-operator/workspace/memory/knowledge/references/routing/`  
  (or `.../chief-orchestrator/...` if the profile was never renamed)
- **Droplet:** `/home/hermesuser/.hermes/profiles/chief-orchestrator-droplet/workspace/memory/knowledge/references/routing/`

It is **normal** for the materialized tree to be missing until you sync; the **canonical** copies are always in the **git repo** paths above.

## Also linked from

- `memory/knowledge/references/index/memory-network.md`
- `memory/knowledge/README.md`
- `memory/knowledge/domains/workspace-and-runtime-map.md`
