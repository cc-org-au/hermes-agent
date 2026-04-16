#!/usr/bin/env bash
# From your Mac: install append_operator_authorized_key.sh on the operator mini (~/.ssh/),
# then run it there (interactive or pass the collaborator's single output line).
#
# Uses scripts/core/ssh_operator.sh and ~/.env/.env (MACMINI_SSH_*).
#
# Usage:
#   ./run_append_operator_authorized_key_on_mini.sh
#       Push script if needed, then open interactive append on the mini (TTY).
#   ./run_append_operator_authorized_key_on_mini.sh 'ssh-ed25519 AAAA...'
#       Non-interactive: append a plain unrestricted pubkey line to operator's authorized_keys.
#   ./run_append_operator_authorized_key_on_mini.sh 'from="100.x/32" ssh-ed25519 AAAA...'
#       Non-interactive: append that exact line to operator's authorized_keys on the mini.
#   ./run_append_operator_authorized_key_on_mini.sh 'ssh-ed25519 AAAA...' '100.x.x.x/32'
#       Non-interactive: pubkey + optional from CIDR.
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMES_AGENT_REPO:-}"
if [[ -z "$REPO_ROOT" ]]; then
  _d="$ROOT"
  while [[ "$_d" != "/" ]]; do
    if [[ -f "$_d/scripts/core/ssh_operator.sh" ]]; then
      REPO_ROOT="$_d"
      break
    fi
    _d="$(dirname "$_d")"
  done
fi
REPO_ROOT="${REPO_ROOT:-${HOME}/hermes-agent}"
SSH_OP="${REPO_ROOT}/scripts/core/ssh_operator.sh"
APPEND_SRC="${ROOT}/append_operator_authorized_key.sh"
[[ -f "$APPEND_SRC" ]] || APPEND_SRC="${REPO_ROOT}/scripts/core/append_operator_authorized_key.sh"
if [[ ! -f "$SSH_OP" ]]; then
  echo "Cannot find ssh_operator.sh (set HERMES_AGENT_REPO or run from repo scripts/core)." >&2
  exit 1
fi
if [[ ! -f "$APPEND_SRC" ]]; then
  echo "Cannot find append_operator_authorized_key.sh next to this script or under scripts/core." >&2
  exit 1
fi

echo ">>> Installing ~/.ssh/append_operator_authorized_key.sh on operator mini (ssh -T) ..."
HERMES_OPERATOR_SSH_NO_TTY=1 "$SSH_OP" 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && umask 077 && cat > ~/.ssh/append_operator_authorized_key.sh && chmod 700 ~/.ssh/append_operator_authorized_key.sh' <"$APPEND_SRC"

if [[ $# -eq 0 ]]; then
  echo ">>> Running interactive append on mini (use a real terminal if paste fails) ..."
  "$SSH_OP" 'bash ~/.ssh/append_operator_authorized_key.sh'
  exit $?
fi

REMOTE_CMD="bash ~/.ssh/append_operator_authorized_key.sh"
for _a in "$@"; do
  REMOTE_CMD+=" $(printf '%q' "$_a")"
done
echo ">>> Appending on mini (non-interactive) ..."
HERMES_OPERATOR_SSH_NO_TTY=1 "$SSH_OP" "$REMOTE_CMD"
