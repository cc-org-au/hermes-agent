# Governance context (agentic company policy pack)

This file lives at `HERMES_HOME/.hermes.md`. Hermes loads it **first** in project context (before cwd `.hermes.md` / `AGENTS.md`), so paths stay visible when `MESSAGING_CWD` or the shell cwd is not the policy tree.

## Where materialized files live (absolute paths on this host)

- **Workspace root (start here for runtime pack):** `{{WORKSPACE_ROOT}}`
  - **Bootstrap (read first among runtime files):** `{{WORKSPACE_ROOT}}/BOOTSTRAP.md`
  - **Session / read order:** `{{WORKSPACE_ROOT}}/AGENTS.md`
  - **Layout index:** `{{WORKSPACE_ROOT}}/WORKSPACE.md`
  - **Operations registers:** `{{WORKSPACE_ROOT}}/operations/`
  - **Optional — nested editable policy mirror (pipeline-only):** `{{WORKSPACE_ROOT}}/policies/` — only present if your **activation pipeline** materialized generated or editable policy copies here. **Do not assume this directory exists.** It is **not** the primary policy canon for typical Hermes profiles.

- **Canonical policy bundle (read policies here):** `{{POLICY_ROOT}}`

In **multi-profile** setups (e.g. `chief-orchestrator` + delegate profiles), **`POLICY_ROOT`** should resolve to **`$HERMES_HOME/policies/`** on each profile — usually a **symlink** to **`~/.hermes/profiles/chief-orchestrator/policies`** so every role reads the **same** markdown tree. **Do not** point operators at `workspace/policies/` as the canonical source when **`${HERMES_HOME}/policies/`** is already populated or symlinked.

## How to use this with Hermes

After the pipeline runs, Hermes injects this file plus (when present) the contents of `BOOTSTRAP.md` and `AGENTS.md` under the workspace root into the model context, so the agent knows where policies and runtime files are.

**Governance read order** in the canonical tree: `{{POLICY_ROOT}}/README.md`, then `{{POLICY_ROOT}}/core/security-first-setup.md`, then the sequence in that tree.

**Messaging / gateway health:** There is **one** long-lived `gateway run` per host for the **orchestrator** profile that owns platform tokens (usually **`chief-orchestrator`**). Delegate profiles used only for `delegate_task(..., hermes_profile=…)` **do not** run a separate gateway. Check health with **`hermes -p chief-orchestrator gateway watchdog-check`** (or your sticky orchestrator profile), not per-delegate profiles. See `{{POLICY_ROOT}}/core/gateway-watchdog.md`.
