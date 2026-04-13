#!/usr/bin/env bash
# SSH to operator mini using a break-glass private key (no sshd from= on that pubkey line).
# Key resolution (first hit wins):
#   1) OPERATOR_BREAKGLASS_KEY=file
#   2) $PWD/id_ed25519, $PWD/operator_breakglass, $PWD/breakglass_ed25519
#   3) Script directory: same filenames
#   4) $HOME/.env/.breakglass as FILE (private key PEM/OpenSSH)
#   5) $HOME/.env/.breakglass/id_ed25519 (or operator_breakglass)
#
# Works from any network if you can reach HOST:PORT (use Tailscale IP).
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${OPERATOR_TAILSCALE_HOST:-100.67.17.9}"
PORT="${OPERATOR_SSH_PORT:-52822}"
USER_NAME="${OPERATOR_SSH_USER:-operator}"

_resolve_breakglass_key() {
  local f
  if [[ -n "${OPERATOR_BREAKGLASS_KEY:-}" && -f "${OPERATOR_BREAKGLASS_KEY}" ]]; then
    echo "${OPERATOR_BREAKGLASS_KEY}"
    return 0
  fi
  for f in \
    "${PWD}/id_ed25519" \
    "${PWD}/operator_breakglass" \
    "${PWD}/breakglass_ed25519" \
    "${SCRIPT_DIR}/id_ed25519" \
    "${SCRIPT_DIR}/operator_breakglass" \
    "${SCRIPT_DIR}/breakglass_ed25519"; do
    if [[ -f "$f" && ! "$f" =~ \.pub$ ]]; then
      echo "$f"
      return 0
    fi
  done
  local bg="${HOME}/.env/.breakglass"
  if [[ -f "$bg" ]]; then
    echo "$bg"
    return 0
  fi
  if [[ -d "$bg" ]]; then
    for f in "$bg/id_ed25519" "$bg/operator_breakglass" "$bg/breakglass_ed25519"; do
      if [[ -f "$f" ]]; then
        echo "$f"
        return 0
      fi
    done
  fi
  return 1
}

KEY="$(_resolve_breakglass_key || true)"
if [[ -z "$KEY" ]]; then
  echo "No break-glass private key found." >&2
  echo "Set OPERATOR_BREAKGLASS_KEY, put id_ed25519 in this directory (${PWD}), script dir (${SCRIPT_DIR}), or ~/.env/.breakglass (file or dir with id_ed25519)." >&2
  exit 1
fi
exec ssh -o IdentitiesOnly=yes -o IdentityAgent=none -i "$KEY" -p "$PORT" "$USER_NAME@$HOST" "$@"
