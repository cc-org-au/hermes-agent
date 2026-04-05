#!/usr/bin/env bash
# Ensure the chief-orchestrator profile has ~/.hermes/profiles/chief-orchestrator/.env
#
# Hermes loads secrets from HERMES_HOME/.env only. With `hermes -p chief-orchestrator`,
# HERMES_HOME is the profile directory — a missing profile .env silently falls back to
# the repo's .env (dev) or leaves only shell exports, which breaks `profile show` and
# makes deploys harder to reason about.
#
# Idempotent: if the profile .env already exists, only fixes permissions and exits 0.
# Otherwise copies, in order: ~/.hermes/.env → profile, then $REPO/.env → profile.
#
# Usage (on VPS as hermesuser):
#   ./scripts/ensure_chief_orchestrator_profile_env.sh
#
# Env overrides:
#   HERMES_PROFILE_DIR  — default ~/.hermes/profiles/chief-orchestrator
#   HERMES_AGENT_REPO   — default ~/hermes-agent
set -euo pipefail

PROFILE_DIR="${HERMES_PROFILE_DIR:-$HOME/.hermes/profiles/chief-orchestrator}"
REPO="${HERMES_AGENT_REPO:-$HOME/hermes-agent}"
ENV_TARGET="$PROFILE_DIR/.env"

mkdir -p "$PROFILE_DIR"

if [[ -f "$ENV_TARGET" ]]; then
  chmod 600 "$ENV_TARGET" 2>/dev/null || true
  echo "ensure_chief_orchestrator_profile_env: OK ($ENV_TARGET exists)"
  exit 0
fi

if [[ -f "$HOME/.hermes/.env" ]]; then
  cp "$HOME/.hermes/.env" "$ENV_TARGET"
  chmod 600 "$ENV_TARGET"
  echo "ensure_chief_orchestrator_profile_env: seeded profile .env from ~/.hermes/.env"
  exit 0
fi

if [[ -f "$REPO/.env" ]]; then
  cp "$REPO/.env" "$ENV_TARGET"
  chmod 600 "$ENV_TARGET"
  echo "ensure_chief_orchestrator_profile_env: seeded profile .env from repo .env"
  exit 0
fi

echo "ensure_chief_orchestrator_profile_env: no seed .env found." >&2
echo "  Create $ENV_TARGET (e.g. cp $REPO/.env.example $ENV_TARGET and fill keys)." >&2
exit 1
