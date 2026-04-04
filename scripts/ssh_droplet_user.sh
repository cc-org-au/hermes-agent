#!/usr/bin/env bash
# Open a shell (or run a command) as the normal login user by SSH-ing as the admin user
# (SSH_USER from ~/.env/.env — same pubkey as ssh_droplet.sh), then sudo to that user.
#
# Sudo is interactive (no sudo -S pipe): you type the sudo password on the remote TTY. Piping
# the password into sudo -S breaks interactive login shells (stdin EOF closes the session).
#
# Requires ~/.env/.env: SSH_PORT, SSH_USER, SSH_TAILSCALE_IP (or SSH_IP)
# Same private key as ssh_droplet.sh. Optional: SSH_LOGIN_USER (default: hermesuser).
#
# Usage:
#   ./scripts/ssh_droplet_user.sh              # sudo -i login shell as SSH_LOGIN_USER
#   ./scripts/ssh_droplet_user.sh 'hostname'   # run one command as that user (sudo prompts once)

set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
_LOGIN_USER=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet_user.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_droplet_user.sh: missing key ${KEY_FILE} (set SSH_KEY_FILE)" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP) export "${key}=${val}" ;;
    SSH_LOGIN_USER) _LOGIN_USER="${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
LOGIN_TARGET="${_LOGIN_USER:-${AGENT_DROPLET_RUNTIME_USER:-hermesuser}}"
LU=$(printf '%q' "$LOGIN_TARGET")

REMOTE_BASE=(
  ssh -t -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none
  -o AddKeysToAgent=no -o PreferredAuthentications=publickey
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
  -i "$KEY_FILE" -p "${SSH_PORT:?}"
  "${SSH_USER:?}@${HOST}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  REMOTE_BASE+=(-o UseKeychain=no)
fi
REMOTE=("${REMOTE_BASE[@]}")

unset SSH_PASSPHRASE 2>/dev/null || true
_DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)

if [[ ! -t 0 && "${HERMES_DROPLET_INTERACTIVE:-}" != "1" ]]; then
  echo "ssh_droplet_user.sh: requires an interactive terminal (or HERMES_DROPLET_INTERACTIVE=1)." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "sudo -i -u ${LU}"
fi

INNER=$(printf '%q' "$*")
exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "sudo -u ${LU} -H bash -lc ${INNER}"
