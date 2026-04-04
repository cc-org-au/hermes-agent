#!/usr/bin/env bash
# SSH to the droplet using an encrypted private key.
#
# Expects a shell-env file (default: ~/.env/.env) with at least:
#   SSH_PORT, SSH_USER, SSH_TAILSCALE_IP (or SSH_IP)
# and a private key at ~/.env/.ssh_key unless SSH_KEY_FILE is set.
# Optional: SSH_SUDO_PASSWORD (required for --sudo-user; used only for sudo -S on the remote).
#
# SSH key passphrase — default: entered interactively (or via /dev/tty). ssh-agent and inherited
# SSH_ASKPASS are stripped unless you opt in below.
#
# Opt-in automation (CI / headless): set HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 and put SSH_PASSPHRASE
# in the env file. The script uses a short-lived SSH_ASKPASS helper (never exports SSH_PASSPHRASE to ssh).
# Non-interactive use without that opt-in fails unless HERMES_DROPLET_INTERACTIVE=1.
#
# Usage:
#   ./scripts/ssh_droplet.sh
#   ./scripts/ssh_droplet.sh 'hostname'
#   ./scripts/ssh_droplet.sh --sudo-user hermesuser 'cd ~/hermes-agent && git pull'
#
# Remote side of "<cli> … droplet" (workstation): scripts/hermes → scripts/agent-droplet.
# See policies/core/unified-deployment-and-security.md (Step 15).

set -euo pipefail

_drop_cleanup() {
  [[ -n "${_DROPLET_PASSFILE:-}" && -f "$_DROPLET_PASSFILE" ]] && rm -f "$_DROPLET_PASSFILE"
  [[ -n "${_DROPLET_ASKPASS_SCRIPT:-}" && -f "$_DROPLET_ASKPASS_SCRIPT" ]] && rm -f "$_DROPLET_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
_DROPLET_KEY_PASS=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_droplet.sh: missing key ${KEY_FILE} (set SSH_KEY_FILE)" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|SSH_SUDO_PASSWORD) export "${key}=${val}" ;;
    SSH_PASSPHRASE)
      if [[ "${HERMES_DROPLET_ALLOW_ENV_PASSPHRASE:-}" == "1" ]]; then
        _DROPLET_KEY_PASS="${val}"
      fi
      ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"

# IdentityAgent=none — disable ssh-agent. UseKeychain=no (macOS only) — do not pull key passphrase
# from the login keychain. AddKeysToAgent=no — never add this key to an agent mid-session.
REMOTE_BASE=(
  ssh -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none
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

if [[ "${HERMES_DROPLET_ALLOW_ENV_PASSPHRASE:-}" == "1" ]]; then
  if [[ -z "${_DROPLET_KEY_PASS}" ]]; then
    echo "ssh_droplet.sh: HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 but SSH_PASSPHRASE is missing in ${ENV_FILE}" >&2
    exit 1
  fi
  _DROPLET_PASSFILE=$(mktemp)
  _DROPLET_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_DROPLET_PASSFILE"
  printf '%s' "$_DROPLET_KEY_PASS" > "$_DROPLET_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_DROPLET_PASSFILE'" > "$_DROPLET_ASKPASS_SCRIPT"
  chmod 700 "$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

if [[ ! -t 0 && "${HERMES_DROPLET_INTERACTIVE:-}" != "1" && "${HERMES_DROPLET_ALLOW_ENV_PASSPHRASE:-}" != "1" ]]; then
  echo "ssh_droplet.sh: droplet SSH requires an interactive terminal (or set HERMES_DROPLET_INTERACTIVE=1 if your client exposes /dev/tty for the key passphrase)." >&2
  exit 1
fi

if [[ "${1:-}" == "--sudo-user" ]]; then
  shift
  SUDO_U="${1:?--sudo-user requires a username}"
  shift
  [[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
    echo "ssh_droplet.sh: SSH_SUDO_PASSWORD not set in ${ENV_FILE}" >&2
    exit 1
  }
  PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
  INNER=$(printf '%q' "$*")
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "printf '%s' '${PW_B64}' | base64 -d | sudo -S -u ${SUDO_U} -H bash -lc ${INNER}"
fi

exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "$@"
