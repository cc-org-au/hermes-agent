#!/usr/bin/env bash
# Copy REM-006/007/009 workspace templates into HERMES_HOME/workspace/operations/
# (does not overwrite existing files). Run after materialize_policies_into_hermes_home.sh
# or any time you need the registers on a new profile.
#
# Usage:
#   export HERMES_HOME=/path/to/.hermes   # or profile path
#   ./scripts/materialize_rem_operations.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${HERMES_HOME:?Set HERMES_HOME (e.g. profile directory)}"
SRC="${ROOT}/scripts/templates/rem_operations"
DEST="${HERMES_HOME}/workspace/operations"

if [[ ! -d "$SRC" ]]; then
  echo "materialize_rem: missing template dir $SRC" >&2
  exit 1
fi

mkdir -p "${DEST}/projects/agentic-company"

copy_if_missing() {
  local rel="$1"
  local from="${SRC}/${rel}"
  local to="${DEST}/${rel}"
  mkdir -p "$(dirname "$to")"
  if [[ -f "$to" ]]; then
    echo "materialize_rem: skip (exists) $to"
    return 0
  fi
  cp "$from" "$to"
  echo "materialize_rem: created $to"
}

copy_if_missing "SECURITY_SUBAGENTS_REGISTER.md"
copy_if_missing "FUNCTIONAL_DIRECTORS_REGISTER.md"
copy_if_missing "PROJECT_LEADS_REGISTER.md"
copy_if_missing "projects/agentic-company/README.md"

echo "materialize_rem: done DEST=$DEST"
