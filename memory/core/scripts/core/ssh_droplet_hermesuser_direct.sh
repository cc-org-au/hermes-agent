#!/usr/bin/env bash
# OpenSSH directly as hermesuser@<host> — normal remote login shell (no admin hop, no sudo).
#
# Requires the same key in hermesuser's ~/.ssh/authorized_keys on the server. If you only have
# admin SSH access, use ./scripts/core/ssh_droplet_user.sh instead (SSH as admin, sudo to hermesuser).
#
# Expects ~/.env/.env: SSH_TAILSCALE_IP (or SSH_IP); optional SSH_PORT (default 40227)
# Key: same resolution as ssh_droplet.sh (SSH_KEY_FILE in env file, ~/.env/.ssh_key, ~/.env/.ssh_droplet_key).
# Optional: SSH_LOGIN_USER (default hermesuser) — remote account to SSH as.
# Optional: HERMES_DROPLET_REPO, HERMES_DROPLET_VENV_USER — same as ssh_droplet_user.sh (venv on login).
#
# Optional headless key unlock (same as ssh_droplet.sh): in ~/.env/.env set
#   HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1
#   SSH_PASSPHRASE=...
#
# Usage:
#   ./scripts/core/ssh_droplet_hermesuser_direct.sh
#   ./scripts/core/ssh_droplet_hermesuser_direct.sh 'hostname'

set -euo pipefail

_drop_cleanup() {
  [[ -n "${_DROPLET_PASSFILE:-}" && -f "$_DROPLET_PASSFILE" ]] && rm -f "$_DROPLET_PASSFILE"
  [[ -n "${_DROPLET_ASKPASS_SCRIPT:-}" && -f "$_DROPLET_ASKPASS_SCRIPT" ]] && rm -f "$_DROPLET_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
_LOGIN_USER=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet_hermesuser_direct.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
  exit 1
fi

_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=droplet_remote_venv.sh
source "${_SCRIPTS_DIR}/droplet_remote_venv.sh"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  if [[ "$key" == export* ]]; then
    key="${key#export}"
    key="${key##[[:space:]]}"
    key="${key%%[[:space:]]}"
  fi
  if [[ "$val" =~ ^\"(.*)\"$ ]]; then
    val="${BASH_REMATCH[1]}"
  fi
  case "$key" in
    SSH_PORT|SSH_TAILSCALE_IP|SSH_IP|HERMES_DROPLET_REPO|HERMES_DROPLET_VENV_USER|\
    SSH_PORT_DROPLET|SSH_TAILSCALE_IP_DROPLET|SSH_IP_DROPLET|SSH_TAILSCALE_DNS_DROPLET)
      export "${key}=${val}"
      ;;
    SSH_KEY_FILE|SSH_KEY_DROPLET)
      export SSH_KEY_FILE="${val}"
      ;;
    SSH_LOGIN_USER) _LOGIN_USER="${val}" ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done < "$ENV_FILE"

if ! KEY_FILE="$(droplet_resolve_ssh_key_file)"; then
  echo "ssh_droplet_hermesuser_direct.sh: no private key found. Set SSH_KEY_FILE or SSH_KEY_DROPLET in ${ENV_FILE}, export SSH_KEY_FILE, or use ~/.env/.ssh_key or ~/.env/.ssh_droplet_key" >&2
  exit 1
fi

if [[ -z "${SSH_TAILSCALE_IP:-}" && -n "${SSH_TAILSCALE_IP_DROPLET:-}" ]]; then SSH_TAILSCALE_IP="${SSH_TAILSCALE_IP_DROPLET}"; export SSH_TAILSCALE_IP; fi
if [[ -z "${SSH_IP:-}" && -n "${SSH_IP_DROPLET:-}" ]]; then SSH_IP="${SSH_IP_DROPLET}"; export SSH_IP; fi
if [[ -z "${SSH_PORT:-}" && -n "${SSH_PORT_DROPLET:-}" ]]; then SSH_PORT="${SSH_PORT_DROPLET}"; export SSH_PORT; fi

SSH_PORT="${SSH_PORT:-40227}"
export SSH_PORT

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:-${SSH_TAILSCALE_DNS_DROPLET:-}}}"
if [[ -z "$HOST" ]]; then
  echo "ssh_droplet_hermesuser_direct.sh: set SSH_TAILSCALE_IP, SSH_IP, or SSH_TAILSCALE_DNS_DROPLET (or *_DROPLET aliases) in ${ENV_FILE}" >&2
  exit 1
fi
REMOTE_USER="${_LOGIN_USER:-${AGENT_DROPLET_RUNTIME_USER:-hermesuser}}"

REMOTE_BASE=(
  ssh -tt -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none
  -o AddKeysToAgent=no -o ControlMaster=no -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
  -i "$KEY_FILE" -p "${SSH_PORT}"
  "${REMOTE_USER}@${HOST}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  REMOTE_BASE+=(-o UseKeychain=no)
fi
REMOTE=("${REMOTE_BASE[@]}")

unset SSH_PASSPHRASE 2>/dev/null || true
_DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)

if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" ]]; then
  if [[ -z "${_RAW_SSH_PASSPHRASE}" ]]; then
    echo "ssh_droplet_hermesuser_direct.sh: HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 but SSH_PASSPHRASE missing in ${ENV_FILE}" >&2
    exit 1
  fi
  _DROPLET_PASSFILE=$(mktemp)
  _DROPLET_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_DROPLET_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_DROPLET_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_DROPLET_PASSFILE'" > "$_DROPLET_ASKPASS_SCRIPT"
  chmod 700 "$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_DROPLET_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _DROPLET_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

if [[ ! -t 0 && "${HERMES_DROPLET_INTERACTIVE:-}" != "1" && "$_ALLOW_ENV_PASS_FROM_FILE" != "1" ]]; then
  echo "ssh_droplet_hermesuser_direct.sh: needs a TTY (or HERMES_DROPLET_INTERACTIVE=1, or env-file passphrase mode)." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  _INNER="exec bash -l"
  if _droplet_venv_user_matches "$REMOTE_USER"; then
    _INNER=$(_droplet_wrap_cmd_with_venv "$_INNER")
  fi
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "bash -lc $(printf '%q' "$_INNER")"
fi

_USER_CMD="$*"
if _droplet_venv_user_matches "$REMOTE_USER"; then
  _USER_CMD=$(_droplet_wrap_cmd_with_venv "$_USER_CMD")
fi
exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "bash -lc $(printf '%q' "$_USER_CMD")"
