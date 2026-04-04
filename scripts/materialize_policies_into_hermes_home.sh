#!/usr/bin/env bash
# Materialize repo policies/ into HERMES_HOME/policies and HERMES_HOME/workspace,
# and install HERMES_HOME/.hermes.md so Hermes injects governance context (see agent/prompt_builder.py).
#
# Usage (on the host that has the hermes-agent checkout + venv):
#   export HERMES_HOME=/home/hermesuser/.hermes   # or ~/.hermes
#   ./scripts/materialize_policies_into_hermes_home.sh
#
# Optional: OVERWRITE_HERMES_MD=1 to replace an existing HERMES_HOME/.hermes.md from the template.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${HERMES_HOME:?Set HERMES_HOME to the Hermes profile directory (e.g. /home/hermesuser/.hermes)}"
export HERMES_HOME
PY="${ROOT}/venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="${ROOT}/venv/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  echo "materialize: no venv python at ${ROOT}/venv/bin — activate venv or set PYTHON" >&2
  exit 1
fi
"$PY" "${ROOT}/policies/core/scripts/start_pipeline.py" \
  --workspace-root "${HERMES_HOME}/workspace" \
  --policy-root "${HERMES_HOME}/policies"
TEMPLATE="${ROOT}/scripts/templates/hermes_home_governance.md"
TARGET="${HERMES_HOME}/.hermes.md"
if [[ -f "$TEMPLATE" ]]; then
  if [[ ! -f "$TARGET" ]] || [[ "${OVERWRITE_HERMES_MD:-0}" == "1" ]]; then
    cp "$TEMPLATE" "$TARGET"
    echo "materialize: wrote ${TARGET}"
  else
    echo "materialize: left existing ${TARGET} (set OVERWRITE_HERMES_MD=1 to replace)"
  fi
else
  echo "materialize: template missing: $TEMPLATE" >&2
  exit 1
fi
echo "materialize: done — policy root: ${HERMES_HOME}/policies workspace: ${HERMES_HOME}/workspace"
