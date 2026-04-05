#!/usr/bin/env bash
# Materialize repo policies/ into HERMES_HOME/policies and HERMES_HOME/workspace,
# write path-filled HERMES_HOME/.hermes.md, and lay runtime pack files at the workspace
# root (BOOTSTRAP.md, AGENTS.md, …) so Hermes can load them (see agent/prompt_builder.py).
#
# After materialization, links HERMES_HOME/SOUL.md -> workspace/SOUL.md so load_soul_md()
# (agent/prompt_builder.py) and the materialized pack stay in sync.
#
# Usage (on the host that has the hermes-agent checkout + venv):
#   export HERMES_HOME=/home/hermesuser/.hermes
#   ./scripts/materialize_policies_into_hermes_home.sh
#
# Chief orchestrator profile (same as agent-droplet default HERMES_HOME layout):
#   HERMES_PROFILE=chief-orchestrator HERMES_PROFILE_BASE=/home/hermesuser/.hermes \
#     ./scripts/materialize_policies_into_hermes_home.sh
#   (HERMES_PROFILE_BASE defaults to $HOME/.hermes when unset — set it when sudo SSH uses a different $HOME.)
#
# Optional: SKIP_GOVERNANCE_MD=1 to skip writing HERMES_HOME/.hermes.md (paths-only stub).
# Optional: SKIP_SOUL_SYMLINK=1 to skip creating HERMES_HOME/SOUL.md -> workspace/SOUL.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${HERMES_PROFILE:-}" ]]; then
  if [[ -n "${HERMES_PROFILE_BASE:-}" ]]; then
    _base="${HERMES_PROFILE_BASE}"
  elif [[ -n "${HERMES_HOME:-}" ]] && [[ "${HERMES_HOME}" != *"/profiles/"* ]]; then
    _base="${HERMES_HOME}"
  else
    _base="${HOME}/.hermes"
  fi
  export HERMES_HOME="${_base%/}/profiles/${HERMES_PROFILE}"
fi
: "${HERMES_HOME:?Set HERMES_HOME, or set HERMES_PROFILE (optional HERMES_PROFILE_BASE, default \$HOME/.hermes)}"
export HERMES_HOME
mkdir -p "${HERMES_HOME}"
PY="${ROOT}/venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="${ROOT}/venv/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  echo "materialize: no venv python at ${ROOT}/venv/bin — activate venv or set PYTHON" >&2
  exit 1
fi
ARGS=(
  "${ROOT}/policies/core/scripts/start_pipeline.py"
  --workspace-root "${HERMES_HOME}/workspace"
  --policy-root "${HERMES_HOME}/policies"
)
if [[ "${SKIP_GOVERNANCE_MD:-0}" != "1" ]]; then
  ARGS+=(--write-governance-md "${HERMES_HOME}/.hermes.md")
fi
"$PY" "${ARGS[@]}"

if [[ -x "${ROOT}/scripts/materialize_rem_operations.sh" ]]; then
  bash "${ROOT}/scripts/materialize_rem_operations.sh"
fi

_ws_soul="${HERMES_HOME}/workspace/SOUL.md"
_home_soul="${HERMES_HOME}/SOUL.md"
if [[ "${SKIP_SOUL_SYMLINK:-0}" != "1" ]]; then
  if [[ -f "${_ws_soul}" ]]; then
    ln -sfn "workspace/SOUL.md" "${_home_soul}"
    echo "materialize: SOUL.md -> workspace/SOUL.md (symlink at ${HERMES_HOME}/SOUL.md)"
  else
    echo "materialize: warning: ${_ws_soul} missing — SOUL symlink skipped" >&2
  fi
fi

echo "materialize: done — HERMES_HOME=${HERMES_HOME} policy root: ${HERMES_HOME}/policies workspace: ${HERMES_HOME}/workspace (flat runtime files at workspace root)"
