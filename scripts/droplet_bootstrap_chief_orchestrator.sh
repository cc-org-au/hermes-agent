#!/usr/bin/env bash
# Run on the VPS (e.g. as hermesuser) after cloning hermes-agent and creating venv.
# Creates ~/.hermes/profiles/chief-orchestrator if missing and runs: hermes profile use chief-orchestrator
#
# Usage:
#   cd ~/hermes-agent && ./scripts/droplet_bootstrap_chief_orchestrator.sh
#
# Uses python -m hermes_cli.main so PATH does not need venv/bin/hermes.
#
# `-p default` is required: if the sticky profile is already chief-orchestrator,
# Hermes sets HERMES_HOME to that profile before subcommands run; `profile create`
# would then incorrectly think chief-orchestrator already exists at the active path.
set -euo pipefail
REPO="${HERMES_AGENT_REPO:-$HOME/hermes-agent}"
cd "$REPO"
PY="${HERMES_PYTHON:-$REPO/venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "droplet_bootstrap_chief_orchestrator.sh: no interpreter at ${PY} (set HERMES_PYTHON)" >&2
  exit 1
fi
"$PY" -m hermes_cli.main -p default profile create chief-orchestrator --no-alias || true
"$PY" -m hermes_cli.main -p default profile use chief-orchestrator
"$PY" -m hermes_cli.main -p default profile show chief-orchestrator
