# Governance context (agentic company policy pack)

This file lives at `HERMES_HOME/.hermes.md`. Hermes loads it **in addition to** any project `.hermes.md` / `AGENTS.md` in the working directory, so policy paths stay visible when `MESSAGING_CWD` or the shell cwd is not the policy tree.

**Canonical policy bundle (read-mostly):** `HERMES_HOME/policies/` — full repository `policies/` tree materialized by `policies/core/scripts/start_pipeline.py`.

**Runtime-editable copy + operations:** `HERMES_HOME/workspace/` — includes `workspace/policies/` (generated + runtime agent markdown) and `workspace/operations/` (org registers, `projects/` roots).

**Read order:** start at `HERMES_HOME/policies/README.md`, then `HERMES_HOME/policies/core/security-first-setup.md`, then the governance read-order sequence in that tree.

For production messaging uptime, after deployment handoff see `HERMES_HOME/policies/core/gateway-watchdog.md` and `hermes gateway watchdog-check`.
