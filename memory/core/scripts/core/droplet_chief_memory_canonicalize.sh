#!/usr/bin/env bash
# Wrapper: same as operator_chief_memory_canonicalize.sh with HERMES_CANONICAL_HOST_LABEL=droplet.
# Run on the VPS as hermesuser, or via droplet_run.sh --droplet-require-sudo --sudo-user hermesuser '…'
set -euo pipefail
export HERMES_CANONICAL_HOST_LABEL=droplet
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$_SCRIPT_DIR/operator_chief_memory_canonicalize.sh" "$@"
