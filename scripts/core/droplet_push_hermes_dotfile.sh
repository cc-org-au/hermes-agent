#!/usr/bin/env bash
# Copy local ~/.hermes/.hermes to /home/hermesuser/.hermes/.hermes on the droplet.
# Backs up the remote file to .hermes.backup.<timestamp> first.
# Uses ~/.env/.env (SSH_*), key, and SSH_SUDO_PASSWORD like droplet_push_hermes_home.sh.
#
# Usage:
#   ./scripts/core/droplet_push_hermes_dotfile.sh
#   HERMES_LOCAL_HERMES_DOTFILE=/path/to/file ./scripts/core/droplet_push_hermes_dotfile.sh
#
set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
LOCAL="${HERMES_LOCAL_HERMES_DOTFILE:-${HOME}/.hermes/.hermes}"
REMOTE_DOT="/home/hermesuser/.hermes/.hermes"

if [[ ! -f "$LOCAL" ]]; then
  echo "droplet_push_hermes_dotfile.sh: missing local file: ${LOCAL}" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]] || [[ ! -f "$KEY_FILE" ]]; then
  echo "droplet_push_hermes_dotfile.sh: need ${ENV_FILE} and ${KEY_FILE}" >&2
  exit 1
fi

SSH_SUDO_PASSWORD=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|SSH_SUDO_PASSWORD) export "${key}=${val}" ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
REMOTE_USER="${SSH_USER:?}"

SSH_BASE=(
  ssh -T
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=30
  -i "$KEY_FILE"
  -p "${SSH_PORT:?}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  SSH_BASE+=(-o UseKeychain=no)
fi

SCP_BASE=(
  scp
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=30
  -i "$KEY_FILE"
  -P "${SSH_PORT:?}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  SCP_BASE+=(-o UseKeychain=no)
fi

_drop_cleanup() {
  [[ -n "${_PUSH_PASSFILE:-}" && -f "$_PUSH_PASSFILE" ]] && rm -f "$_PUSH_PASSFILE"
  [[ -n "${_PUSH_ASKPASS_SCRIPT:-}" && -f "$_PUSH_ASKPASS_SCRIPT" ]] && rm -f "$_PUSH_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

_SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _PUSH_PASSFILE=$(mktemp)
  _PUSH_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_PUSH_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_PUSH_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_PUSH_PASSFILE'" > "$_PUSH_ASKPASS_SCRIPT"
  chmod 700 "$_PUSH_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_PUSH_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

[[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
  echo "droplet_push_hermes_dotfile.sh: SSH_SUDO_PASSWORD must be set in ${ENV_FILE} for remote sudo." >&2
  exit 1
}

UPLOAD="/tmp/hermes-dotfile-$$.upload"
echo "Uploading ${LOCAL} -> ${REMOTE_USER}@${HOST}:${UPLOAD}"
"${_SSH_ENV[@]}" "${SCP_BASE[@]}" "$LOCAL" "${REMOTE_USER}@${HOST}:${UPLOAD}"

PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
TS=$(date +%Y%m%d%H%M%S)

echo "Installing on droplet (backup if ${REMOTE_DOT} exists) ..."
"${_SSH_ENV[@]}" "${SSH_BASE[@]}" "${REMOTE_USER}@${HOST}" \
  "export _H_UP=$(printf '%q' "$UPLOAD") _H_DEST=$(printf '%q' "$REMOTE_DOT") _H_TS=$(printf '%q' "$TS") _H_PW=$(printf '%q' "$PW_B64"); bash -s" <<'EOS'
set -euo pipefail
sudo_s() { printf '%s' "$_H_PW" | base64 -d | sudo -S "$@"; }
sudo_s mkdir -p /home/hermesuser/.hermes
if [[ -f "$_H_DEST" ]]; then
  sudo_s cp -a "$_H_DEST" "${_H_DEST}.backup.${_H_TS}"
  echo "Backed up remote to ${_H_DEST}.backup.${_H_TS}"
fi
sudo_s cp "$_H_UP" "$_H_DEST"
sudo_s chown hermesuser:hermesuser "$_H_DEST"
sudo_s chmod 600 "$_H_DEST" 2>/dev/null || true
sudo_s rm -f "$_H_UP"
echo "droplet_push_hermes_dotfile: installed ${_H_DEST}"
EOS

echo "Done. Local source: ${LOCAL}"
