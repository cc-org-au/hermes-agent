#!/usr/bin/env bash
# Stream /home/hermesuser/hermes-agent and /home/hermesuser/.hermes from the droplet to a Mac
# (default: operator@<tailscale-or-lan-ip>) using the same credential layout as ssh_droplet /
# droplet_pull_hermes_home: workstation ~/.env/.env (SSH_* + SSH_SUDO_PASSWORD) and ~/.env/.ssh_key.
#
# Runs from your workstation (e.g. main Mac). Uses ssh -T on the droplet side so tar streams stay clean.
#
# Add to ~/.env/.env (same file as droplet):
#   MACMINI_SSH_USER=operator
#   MACMINI_SSH_HOST=100.x.y.z          # Tailscale IP of the Mac mini (preferred)
#   MACMINI_SSH_PORT=22                 # optional, default 22
#   MACMINI_SSH_KEY=...                 # optional; defaults to SSH_KEY_FILE / ~/.env/.ssh_key
#   MACMINI_REPO=                       # optional; default remote $HOME/hermes-agent
#
# Repo archive excludes heavy / non-portable trees (recreate venv on the mini: python3 -m venv venv && …).
# Override: export SYNC_REPO_EXCLUDES="venv local_models/hub" (space-separated --exclude names).
#
# WARNING: Copying the droplet ~/.hermes includes gateway state and messaging tokens. Do not run a second
# Hermes gateway with the same bot tokens while the droplet gateway is up — use a different profile or
# stop one gateway first (see AGENTS.md / droplet_pull_hermes_home.sh notes).
#
# On the Mac mini, set HERMES_GATEWAY_LOCK_INSTANCE=mac-mini (launchd or ~/.hermes/.env) so messaging
# token locks use ~/.local/state/hermes/gateway-locks/mac-mini/ instead of the default directory (isolates
# lock files from other hosts; you still must not double-run the same Telegram/Slack tokens).
#
# Usage:
#   ./scripts/core/sync_droplet_to_macmini.sh
#   ./scripts/core/sync_droplet_to_macmini.sh --dry-run
#
set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

if [[ ! -f "$ENV_FILE" ]]; then
  echo "sync_droplet_to_macmini.sh: missing ${ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "sync_droplet_to_macmini.sh: missing key ${KEY_FILE}" >&2
  exit 1
fi

SSH_SUDO_PASSWORD=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""
MACMINI_SSH_USER=""
MACMINI_SSH_HOST=""
MACMINI_SSH_PORT="22"
MACMINI_SSH_KEY=""
MACMINI_REPO=""

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
    MACMINI_SSH_USER) MACMINI_SSH_USER="${val}" ;;
    MACMINI_SSH_HOST) MACMINI_SSH_HOST="${val}" ;;
    MACMINI_SSH_PORT) MACMINI_SSH_PORT="${val}" ;;
    MACMINI_SSH_KEY) MACMINI_SSH_KEY="${val}" ;;
    MACMINI_REPO) MACMINI_REPO="${val}" ;;
  esac
done < "$ENV_FILE"

DROPLET_HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
DROPLET_USER="${SSH_USER:?}"
MINI_USER="${MACMINI_SSH_USER:-operator}"
MINI_HOST="${MACMINI_SSH_HOST:?set MACMINI_SSH_HOST in ${ENV_FILE}}"
MINI_PORT="${MACMINI_SSH_PORT:-22}"
MINI_KEY="${MACMINI_SSH_KEY:-$KEY_FILE}"

[[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
  echo "sync_droplet_to_macmini.sh: SSH_SUDO_PASSWORD required in ${ENV_FILE} for remote sudo tar from hermesuser paths." >&2
  exit 1
}

_ssh_base_array() {
  # Bash 3.2–safe: assign global SSH_CMD_ARRAY from key path + port.
  local key_path="$1" port="$2"
  SSH_CMD_ARRAY=(
    ssh -T
    -o BatchMode=no
    -o IdentitiesOnly=yes
    -o IdentityAgent=none
    -o AddKeysToAgent=no
    -o ControlMaster=no
    -o ControlPath=none
    -o StrictHostKeyChecking=accept-new
    -o ConnectTimeout=30
    -o ServerAliveInterval=10
    -o ServerAliveCountMax=30
    -o TCPKeepAlive=yes
    -i "$key_path"
    -p "$port"
  )
  if [[ "$(uname -s)" == "Darwin" ]]; then
    SSH_CMD_ARRAY+=(-o UseKeychain=no)
  fi
}

_ssh_base_array "$KEY_FILE" "${SSH_PORT:?}"
SSH_DROPLET=("${SSH_CMD_ARRAY[@]}")
_ssh_base_array "$MINI_KEY" "$MINI_PORT"
SSH_MINI=("${SSH_CMD_ARRAY[@]}")

_drop_cleanup() {
  [[ -n "${_SYNC_PASSFILE:-}" && -f "$_SYNC_PASSFILE" ]] && rm -f "$_SYNC_PASSFILE"
  [[ -n "${_SYNC_ASKPASS_SCRIPT:-}" && -f "$_SYNC_ASKPASS_SCRIPT" ]] && rm -f "$_SYNC_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

_SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _SYNC_PASSFILE=$(mktemp)
  _SYNC_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_SYNC_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_SYNC_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_SYNC_PASSFILE'" > "$_SYNC_ASKPASS_SCRIPT"
  chmod 700 "$_SYNC_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_SYNC_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')

_EXCLUDES=(--exclude=venv --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache)
if [[ -n "${SYNC_REPO_EXCLUDES:-}" ]]; then
  _EXCLUDES=()
  for x in $SYNC_REPO_EXCLUDES; do
    _EXCLUDES+=(--exclude="$x")
  done
fi

# Build exclude args for remote tar (single line for sudo bash -lc).
EXCL_REMOTE=""
for x in "${_EXCLUDES[@]}"; do
  EXCL_REMOTE+=" ${x// /\\ }"
done

REMOTE_TAR_REPO="printf '%s' '${PW_B64}' | base64 -d | sudo -S tar czf - ${EXCL_REMOTE} -C /home/hermesuser/hermes-agent ."
REMOTE_TAR_HERMES="printf '%s' '${PW_B64}' | base64 -d | sudo -S tar czf - -C /home/hermesuser .hermes"

if [[ -n "${MACMINI_REPO:-}" ]]; then
  _Q_REPO=$(printf '%q' "$MACMINI_REPO")
  REMOTE_REPO_EXTRACT="mkdir -p ${_Q_REPO} && tar xzf - -C ${_Q_REPO}"
else
  REMOTE_REPO_EXTRACT='mkdir -p "$HOME/hermes-agent" && tar xzf - -C "$HOME/hermes-agent"'
fi
REMOTE_HERMES_EXTRACT='tar xzf - -C "$HOME"'

if [[ "$DRY" == "1" ]]; then
  echo "Would stream repo from ${DROPLET_USER}@${DROPLET_HOST} -> ${MINI_USER}@${MINI_HOST}:${MINI_PORT}"
  echo "  remote extract: ${REMOTE_REPO_EXTRACT}"
  echo "Would stream .hermes from droplet -> ${MINI_USER}@${MINI_HOST} (into \$HOME)"
  echo "  remote extract: ${REMOTE_HERMES_EXTRACT}"
  exit 0
fi

echo ">>> Sync hermes-agent checkout (droplet -> Mac mini) ..."
if ! "${_SSH_ENV[@]}" "${SSH_DROPLET[@]}" "${DROPLET_USER}@${DROPLET_HOST}" "bash -lc $(printf '%q' "$REMOTE_TAR_REPO")" \
  | "${_SSH_ENV[@]}" "${SSH_MINI[@]}" "${MINI_USER}@${MINI_HOST}" "bash -lc $(printf '%q' "$REMOTE_REPO_EXTRACT")"; then
  echo "sync_droplet_to_macmini.sh: repo stream failed" >&2
  exit 1
fi

echo ">>> Sync hermesuser .hermes (droplet -> Mac mini) ..."
if ! "${_SSH_ENV[@]}" "${SSH_DROPLET[@]}" "${DROPLET_USER}@${DROPLET_HOST}" "bash -lc $(printf '%q' "$REMOTE_TAR_HERMES")" \
  | "${_SSH_ENV[@]}" "${SSH_MINI[@]}" "${MINI_USER}@${MINI_HOST}" "bash -lc $(printf '%q' "$REMOTE_HERMES_EXTRACT")"; then
  echo "sync_droplet_to_macmini.sh: .hermes stream failed" >&2
  exit 1
fi

echo ">>> Clearing stale gateway.pid files under ~/.hermes on Mac mini (if any) ..."
"${_SSH_ENV[@]}" "${SSH_MINI[@]}" "${MINI_USER}@${MINI_HOST}" \
  "bash -lc 'rm -f \"\$HOME/.hermes/gateway.pid\" \"\$HOME/.hermes/profiles/\"*/gateway.pid 2>/dev/null || true'"

echo "Done."
echo "On the Mac mini: cd ~/hermes-agent && python3 -m venv venv && ./venv/bin/pip install -U pip && ./venv/bin/pip install -e ."
echo "(or match your droplet install steps). Do not duplicate live gateways with the same tokens as the VPS."
