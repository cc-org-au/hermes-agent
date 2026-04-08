#!/usr/bin/env bash
# SSH to the droplet as the admin user (SSH_USER), optionally sudo to hermesuser (or --sudo-user).
#
# Credentials (never committed): load from HERMES_DROPLET_ENV or ~/.env/.env — same layout as
# ssh_droplet_user.sh / droplet_pull_hermes_home.sh:
#   SSH_PORT, SSH_USER, SSH_TAILSCALE_IP (or SSH_IP), optional SSH_SUDO_PASSWORD,
#   optional HERMES_DROPLET_ALLOW_ENV_PASSPHRASE + SSH_PASSPHRASE for encrypted keys without TTY.
# Private key: SSH_KEY_FILE or ~/.env/.ssh_key
#
# HERMES_DROPLET_WORKSTATION_CLI=1 (set by `hermes … droplet`): do not use env-file SSH_PASSPHRASE /
# ASKPASS — type the key passphrase at the prompt.
#
# Usage:
#   ./scripts/core/ssh_droplet.sh 'hostname'
#   ./scripts/core/ssh_droplet.sh --droplet-require-sudo --sudo-user hermesuser 'whoami'
#   HERMES_DROPLET_REQUIRE_SUDO=1 ./scripts/core/ssh_droplet.sh 'cd ~/hermes-agent && git status'
#
set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=droplet_remote_venv.sh
source "${_SCRIPTS_DIR}/droplet_remote_venv.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_droplet.sh: missing key ${KEY_FILE} (set SSH_KEY_FILE)" >&2
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
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|HERMES_DROPLET_REPO|HERMES_DROPLET_VENV_USER)
      export "${key}=${val}"
      ;;
    SSH_SUDO_PASSWORD) SSH_SUDO_PASSWORD="${val}" ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
NEED_SUDO=0
[[ "${HERMES_DROPLET_REQUIRE_SUDO:-0}" == "1" ]] && NEED_SUDO=1
SUDO_AS="${HERMES_DROPLET_VENV_USER:-hermesuser}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --droplet-require-sudo)
      NEED_SUDO=1
      shift
      ;;
    --droplet-no-sudo)
      NEED_SUDO=0
      shift
      ;;
    --sudo-user)
      SUDO_AS="${2:?--sudo-user requires a username}"
      NEED_SUDO=1
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ "${HERMES_DROPLET_WORKSTATION_CLI:-0}" == "1" ]]; then
  _ALLOW_ENV_PASS_FROM_FILE=0
  _RAW_SSH_PASSPHRASE=""
fi

_drop_cleanup() {
  [[ -n "${_DROPLET_PASSFILE:-}" && -f "$_DROPLET_PASSFILE" ]] && rm -f "$_DROPLET_PASSFILE"
  [[ -n "${_DROPLET_ASKPASS_SCRIPT:-}" && -f "$_DROPLET_ASKPASS_SCRIPT" ]] && rm -f "$_DROPLET_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

_SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _DROPLET_PASSFILE=$(mktemp)
  _DROPLET_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_DROPLET_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_DROPLET_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_DROPLET_PASSFILE'" > "$_DROPLET_ASKPASS_SCRIPT"
  chmod 700 "$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

unset SSH_PASSPHRASE 2>/dev/null || true

_USE_TT=0
if [[ "$NEED_SUDO" == "1" ]] || [[ -t 0 ]] || [[ "${HERMES_DROPLET_INTERACTIVE:-}" == "1" ]]; then
  _USE_TT=1
fi

if [[ "$NEED_SUDO" == "1" ]] && [[ -z "${SSH_SUDO_PASSWORD}" ]]; then
  echo "ssh_droplet.sh: NEED_SUDO but SSH_SUDO_PASSWORD is empty in ${ENV_FILE}" >&2
  exit 1
fi

_SSH_FLAGS=(
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout="${HERMES_DROPLET_SSH_CONNECT_TIMEOUT:-30}"
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=4
  -i "$KEY_FILE"
  -p "${SSH_PORT:?}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  _SSH_FLAGS+=(-o UseKeychain=no)
fi
if [[ "$_USE_TT" == "1" ]]; then
  _SSH_BASE=(ssh -tt "${_SSH_FLAGS[@]}" "${SSH_USER:?}@${HOST}")
else
  _SSH_BASE=(ssh -T "${_SSH_FLAGS[@]}" "${SSH_USER:?}@${HOST}")
fi

_run_remote() {
  local remote_bash_cmd="$1"
  "${_SSH_ENV[@]}" "${_SSH_BASE[@]}" "bash -lc $(printf '%q' "$remote_bash_cmd")"
}

if [[ $# -eq 0 ]]; then
  if [[ "$NEED_SUDO" == "1" ]]; then
    _INNER="exec >/dev/tty 2>&1; exec </dev/tty; exec bash -l"
    _INNER_Q=$(printf '%q' "$_INNER")
    PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
    REMOTE_WRAPPER="printf '%s' '${PW_B64}' | base64 -d | sudo -S -u ${SUDO_AS} -H bash -lc ${_INNER_Q}"
    _run_remote "$REMOTE_WRAPPER"
  else
    _run_remote "exec bash -l"
  fi
  exit $?
fi

_USER_CMD="$*"
if [[ "$NEED_SUDO" == "1" ]]; then
  if _droplet_venv_user_matches "$SUDO_AS"; then
    _USER_CMD=$(_droplet_wrap_cmd_with_venv "$_USER_CMD")
  fi
  # Reattach stdin/stdout/stderr to the SSH TTY after sudo -S so nested TUIs work (AGENTS.md).
  _TTY_FIX='exec >/dev/tty 2>&1; exec </dev/tty; '
  _INNER="${_TTY_FIX}${_USER_CMD}"
  _INNER_Q=$(printf '%q' "$_INNER")
  PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
  REMOTE_WRAPPER="printf '%s' '${PW_B64}' | base64 -d | sudo -S -u ${SUDO_AS} -H bash -lc ${_INNER_Q}"
  _run_remote "$REMOTE_WRAPPER"
else
  _run_remote "$_USER_CMD"
fi
