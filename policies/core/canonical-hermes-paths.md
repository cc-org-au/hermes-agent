# Canonical Hermes paths (operator + agent runtimes)

These paths apply on **both** the operator workstation and the droplet (VPS), and in **every** Hermes profile. Use `display_hermes_home()` / `get_hermes_home()` in code; this document is the human-facing map.

## Top-level (shared, not profile-scoped)

| Purpose | Path |
|--------|------|
| Company / deployment policy tree (canonical sources operators sync from git) | `~/.hermes/policies/` |

Operators may symlink this tree to a chief bundle or keep it as the single checkout of policy text.

## Per-profile (`HERMES_HOME`)

| Purpose | Path |
|--------|------|
| Profile-scoped policy mirror / overlays | `${HERMES_HOME}/policies/` |
| Profile workspace memory (sessions, knowledge, project context) | `${HERMES_HOME}/workspace/memory/` |
| **Operational registers**, governance YAML, messaging overlays, daily budget state | `${HERMES_HOME}/workspace/memory/runtime/operations/` |
| **Project knowledge** (including multi-project company work) | `${HERMES_HOME}/workspace/memory/knowledge/projects/` |

Legacy installs may still use `${HERMES_HOME}/workspace/operations/` until migration; Hermes resolves the canonical directory via `get_workspace_operations_dir()` (see `hermes_constants.py`). Run `scripts/core/migrate_workspace_operations_to_memory_runtime.sh` once per profile after setting `HERMES_HOME`.

## Chief orchestrator (`chief-orchestrator` profile)

Canonical **sources** the chief maintains for **delegation and new profiles**:

- `${HERMES_HOME}/policies/` when `HERMES_HOME` is `~/.hermes/profiles/chief-orchestrator`
- `${HERMES_HOME}/workspace/memory/` (same profile)

When creating or updating **delegate** profiles, copy **the same relative paths** into each delegate’s `${HERMES_HOME}`: `policies/`, `workspace/memory/`, and `workspace/memory/runtime/operations/` as needed for the role. Copy only the **necessary** keys from the chief `.env` into each delegate profile’s `.env`.

Share files across profiles according to task and role (e.g. project leads get relevant `workspace/memory/knowledge/projects/<slug>/` trees).

## Operations templates in the repo

Template and example files for the operations directory live under `memory/runtime/operations/` in this repository; materialize them into each profile’s `${HERMES_HOME}/workspace/memory/runtime/operations/`.

## Projects

The canonical **projects** folder for active work (e.g. **agentic-company**) is:

`HERMES_HOME/workspace/memory/knowledge/projects/`

Copy or link project folders for delegates the same way as other profile-scoped paths.
