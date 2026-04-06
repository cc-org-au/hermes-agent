#!/usr/bin/env bash
# Replace /home/hermesuser/.hermes on the droplet with a tarball of local ~/.hermes.
#
# Uses ssh -T / scp so streams are not corrupted. Same ~/.env/.env as ssh_droplet.sh:
# SSH_*, key file, SSH_SUDO_PASSWORD (remote sudo as hermesadmin).
#
# Backs up the remote tree to /home/hermesuser/.hermes.backup.<timestamp> before replace.
# Runs chown -R hermesuser:hermesuser after extract (Mac UIDs are not valid on Linux).
# Removes stale gateway.pid files under .hermes (Linux vs macOS PID confusion).
#
# Usage:
#   ./scripts/droplet_push_hermes_home.sh              # pack, upload, replace, restart gateway
#   ./scripts/droplet_push_hermes_home.sh --dry-run
#   ./scripts/droplet_push_hermes_home.sh --no-gateway-restart
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
DRY=0
RESTART_GW=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --no-gateway-restart) RESTART_GW=0 ;;
  esac
done

if [[ ! -d "${HOME}/.hermes" ]]; then
  echo "droplet_push_hermes_home.sh: missing ${HOME}/.hermes" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "droplet_push_hermes_home.sh: missing ${ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "droplet_push_hermes_home.sh: missing key ${KEY_FILE}" >&2
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
  [[ -n "${_ARCHIVE:-}" && -f "$_ARCHIVE" ]] && rm -f "$_ARCHIVE"
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
  echo "droplet_push_hermes_home.sh: SSH_SUDO_PASSWORD must be set in ${ENV_FILE} for remote sudo." >&2
  exit 1
}

ARCHIVE="${TMPDIR:-/tmp}/hermes-home-to-droplet.$$".tar.gz
_REMOTE_ARCHIVE="/tmp/hermes-home-push.$$".tar.gz

if [[ "$DRY" == "1" ]]; then
  echo "Would tar ${HOME}/.hermes (excluding .DS_Store) -> ${ARCHIVE}"
  echo "Would scp to ${REMOTE_USER}@${HOST}:${_REMOTE_ARCHIVE}"
  echo "Would backup remote .hermes then extract and chown hermesuser"
  exit 0
fi

echo "Packing ${HOME}/.hermes ..."
# Avoid macOS tar xattrs (Linux tar warns; some versions exit non-zero on pax headers).
if [[ "$(uname -s)" == "Darwin" ]]; then
  export COPYFILE_DISABLE=1
fi
tar czf "$ARCHIVE" \
  --exclude='.DS_Store' \
  --exclude='._*' \
  -C "$HOME" .hermes

if [[ ! -s "$ARCHIVE" ]]; then
  echo "droplet_push_hermes_home.sh: empty archive" >&2
  exit 1
fi

echo "Uploading to ${REMOTE_USER}@${HOST} ..."
"${_SSH_ENV[@]}" "${SCP_BASE[@]}" "$ARCHIVE" "${REMOTE_USER}@${HOST}:${_REMOTE_ARCHIVE}"

PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
TS=$(date +%Y%m%d%H%M%S)
RARCH="${_REMOTE_ARCHIVE}"
# Remote: backup .hermes, extract tarball (paths .hermes/...), fix owner, remove stale PIDs, delete upload.
REMOTE_CMD="set -euo pipefail; \
if [[ -d /home/hermesuser/.hermes ]]; then \
  printf '%s' '${PW_B64}' | base64 -d | sudo -S mv /home/hermesuser/.hermes /home/hermesuser/.hermes.backup.${TS}; \
  echo Remote backup: /home/hermesuser/.hermes.backup.${TS}; \
fi; \
printf '%s' '${PW_B64}' | base64 -d | sudo -S tar xzf '${RARCH}' -C /home/hermesuser; \
printf '%s' '${PW_B64}' | base64 -d | sudo -S chown -R hermesuser:hermesuser /home/hermesuser/.hermes; \
printf '%s' '${PW_B64}' | base64 -d | sudo -S rm -f '${RARCH}'; \
printf '%s' '${PW_B64}' | base64 -d | sudo -S find /home/hermesuser/.hermes -name gateway.pid -delete 2>/dev/null || true; \
printf '%s' '${PW_B64}' | base64 -d | sudo -S find /home/hermesuser/.hermes -name '._*' -type f -delete 2>/dev/null || true; \
echo droplet_push_hermes_home: remote .hermes installed"

echo "Installing on droplet as hermesuser home ..."
if ! "${_SSH_ENV[@]}" "${SSH_BASE[@]}" "${REMOTE_USER}@${HOST}" "bash -lc $(printf '%q' "$REMOTE_CMD")"; then
  echo "droplet_push_hermes_home.sh: remote install failed" >&2
  exit 1
fi

rm -f "$ARCHIVE"
_ARCHIVE=""

if [[ "$RESTART_GW" == "1" ]]; then
  echo "Stopping any running gateway (avoids token lock after replacing .hermes) ..."
  env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
    bash "$ROOT/ssh_droplet.sh" --sudo-user hermesuser \
    'cd ~/hermes-agent && ./venv/bin/python -m hermes_cli.main -p chief-orchestrator gateway stop' \
    || true
  sleep 2
  # Non-systemd `gateway run` orphans (e.g. old nohup) keep Slack/Telegram/WhatsApp scoped locks.
  env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
    bash "$ROOT/ssh_droplet.sh" --sudo-user hermesuser \
    'p=$(pgrep -f "venv/bin/python -m hermes_cli.main.*gateway run" || true); for x in $p; do kill -TERM "$x" 2>/dev/null || true; done; sleep 3; p=$(pgrep -f "venv/bin/python -m hermes_cli.main.*gateway run" || true); for x in $p; do kill -KILL "$x" 2>/dev/null || true; done' \
    || true
  sleep 1
  echo "Restarting gateway (chief-orchestrator profile) ..."
  env HERMES_DROPLET_REQUIRE_SUDO=0 HERMES_DROPLET_INTERACTIVE=1 \
    bash "$ROOT/ssh_droplet.sh" --sudo-user hermesuser \
    'cd ~/hermes-agent && ./venv/bin/python -m hermes_cli.main -p chief-orchestrator gateway restart'
fi

echo "Done. Local was: ${HOME}/.hermes"
echo "If messaging bots share tokens with this Mac, stop one side or use separate profiles."
