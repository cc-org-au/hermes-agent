#!/usr/bin/env bash
# Move legacy HERMES_HOME/workspace/operations → workspace/memory/runtime/operations
# when the new path does not already exist. Safe to re-run: exits 0 if nothing to do.
set -euo pipefail

if [[ -z "${HERMES_HOME:-}" ]]; then
  echo "HERMES_HOME must be set to the profile root (e.g. ~/.hermes/profiles/chief-orchestrator)." >&2
  exit 2
fi

ROOT="${HERMES_HOME/#\~/$HOME}"
ROOT="$(cd "$ROOT" && pwd)"
OLD="$ROOT/workspace/operations"
NEW="$ROOT/workspace/memory/runtime/operations"

if [[ ! -d "$OLD" ]]; then
  echo "Nothing to migrate: missing $OLD"
  exit 0
fi

if [[ -d "$NEW" ]]; then
  echo "Refusing: target already exists: $NEW" >&2
  echo "Merge or remove it, then re-run, or move contents manually." >&2
  exit 1
fi

mkdir -p "$(dirname "$NEW")"
mv "$OLD" "$NEW"
echo "OK: moved $OLD -> $NEW"
