#!/usr/bin/env bash
# Non-interactive SSH to the droplet using an encrypted key + passphrase from env.
#
# Expects a shell-env file (default: ~/.env/.env) with at least:
#   SSH_PASSPHRASE, SSH_PORT, SSH_USER, SSH_TAILSCALE_IP (or SSH_IP)
# and a private key at ~/.env/.ssh_key unless SSH_KEY_FILE is set.
#
# Usage:
#   ./scripts/ssh_droplet.sh
#   ./scripts/ssh_droplet.sh 'hostname'
#   ./scripts/ssh_droplet.sh --sudo-user hermesuser 'cd ~/hermes-agent && git pull'
#     (requires SSH_SUDO_PASSWORD in the env file for sudo -S)

set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_droplet.sh: missing key ${KEY_FILE} (set SSH_KEY_FILE)" >&2
  exit 1
fi

# Do not `source` the whole file: values like SSH_PUBLIC=ssh-ed25519 AAA... (unquoted
# spaces) are invalid bash assignments and break sourcing.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_PASSPHRASE|SSH_TAILSCALE_IP|SSH_IP|SSH_SUDO_PASSWORD) export "${key}=${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
ASK="$(mktemp)"
cleanup() { rm -f "$ASK"; }
trap cleanup EXIT

printf '%s\n' '#!/bin/sh' 'printf %s "$SSH_PASSPHRASE"' > "$ASK"
chmod 700 "$ASK"

export SSH_ASKPASS="$ASK"
export SSH_ASKPASS_REQUIRE=force
export DISPLAY="${DISPLAY:-:0}"

# Keepalive + connect timeout so a hung remote shell does not leave a local ssh
# stuck forever (and Cursor from backgrounding a long-running terminal job).
REMOTE=(ssh -o BatchMode=no -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
  -i "$KEY_FILE" -p "${SSH_PORT:?}" \
  "${SSH_USER:?}@${HOST}")

if [[ "${1:-}" == "--sudo-user" ]]; then
  shift
  SUDO_U="${1:?--sudo-user requires a username}"
  shift
  [[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
    echo "ssh_droplet.sh: SSH_SUDO_PASSWORD not set in ${ENV_FILE}" >&2
    exit 1
  }
  # base64 avoids quoting bugs for sudo password; payload is alphanumeric +/=
  PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
  INNER=$(printf '%q' "$*")
  exec "${REMOTE[@]}" "printf '%s' '${PW_B64}' | base64 -d | sudo -S -u ${SUDO_U} -H bash -lc ${INNER}"
fi

exec "${REMOTE[@]}" "$@"
