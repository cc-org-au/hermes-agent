#!/usr/bin/env bash
# Open a shell (or run a command) as the normal login user by SSH-ing as the admin user
# (SSH_USER from ~/.env/.env — same pubkey as ssh_droplet.sh), then sudo to that user.
#
# If hermesuser can receive SSH directly (same key in authorized_keys), prefer
# ssh_droplet_hermesuser_direct.sh or the shell function `droplet` from scripts/shell/hermes-env.sh.
#
# Sudo is interactive (no sudo -S pipe): you type the sudo password on the remote TTY. Piping
# the password into sudo -S breaks interactive login shells (stdin EOF closes the session).
#
# Requires ~/.env/.env: SSH_USER or SSH_USER_DROPLET; SSH_TAILSCALE_IP, SSH_IP, or SSH_TAILSCALE_DNS_DROPLET
# (or *_DROPLET aliases); optional SSH_PORT (default 40227)
# Same private key as ssh_droplet.sh. Optional: SSH_LOGIN_USER (default: hermesuser).
# Optional: HERMES_DROPLET_REPO (default /home/hermesuser/hermes-agent), HERMES_DROPLET_VENV_USER
# (default hermesuser). Interactive shells and remote commands source that venv when the login
# user matches HERMES_DROPLET_VENV_USER — see policies Step 15 (droplet venv).
#
# Usage:
#   ./scripts/core/ssh_droplet_user.sh              # sudo -i login shell as SSH_LOGIN_USER
#   ./scripts/core/ssh_droplet_user.sh 'hostname'   # run one command as that user (sudo prompts once)
#
# Cursor / automation: prefer ./scripts/core/droplet_run.sh for non-interactive one-offs; use
# droplet_run.sh --droplet-require-sudo --sudo-user hermesuser '…' when SSH_SUDO_PASSWORD is set.
# This script uses interactive sudo (no sudo -S pipe) by design.

set -euo pipefail

ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
_LOGIN_USER=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_droplet_user.sh: missing env file ${ENV_FILE} (set HERMES_DROPLET_ENV)" >&2
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
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|HERMES_DROPLET_REPO|HERMES_DROPLET_VENV_USER|\
    SSH_PORT_DROPLET|SSH_USER_DROPLET|SSH_TAILSCALE_IP_DROPLET|SSH_IP_DROPLET|SSH_TAILSCALE_DNS_DROPLET)
      export "${key}=${val}"
      ;;
    SSH_KEY_FILE|SSH_KEY_DROPLET)
      export SSH_KEY_FILE="${val}"
      ;;
    SSH_LOGIN_USER) _LOGIN_USER="${val}" ;;
  esac
done < "$ENV_FILE"

if ! KEY_FILE="$(droplet_resolve_ssh_key_file)"; then
  echo "ssh_droplet_user.sh: no private key found. Set SSH_KEY_FILE or SSH_KEY_DROPLET in ${ENV_FILE}, export SSH_KEY_FILE, or use ~/.env/.ssh_key or ~/.env/.ssh_droplet_key" >&2
  exit 1
fi

if [[ -z "${SSH_TAILSCALE_IP:-}" && -n "${SSH_TAILSCALE_IP_DROPLET:-}" ]]; then SSH_TAILSCALE_IP="${SSH_TAILSCALE_IP_DROPLET}"; export SSH_TAILSCALE_IP; fi
if [[ -z "${SSH_IP:-}" && -n "${SSH_IP_DROPLET:-}" ]]; then SSH_IP="${SSH_IP_DROPLET}"; export SSH_IP; fi
if [[ -z "${SSH_USER:-}" && -n "${SSH_USER_DROPLET:-}" ]]; then SSH_USER="${SSH_USER_DROPLET}"; export SSH_USER; fi
if [[ -z "${SSH_PORT:-}" && -n "${SSH_PORT_DROPLET:-}" ]]; then SSH_PORT="${SSH_PORT_DROPLET}"; export SSH_PORT; fi

SSH_PORT="${SSH_PORT:-40227}"
export SSH_PORT

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:-${SSH_TAILSCALE_DNS_DROPLET:-}}}"
if [[ -z "$HOST" ]]; then
  echo "ssh_droplet_user.sh: set SSH_TAILSCALE_IP, SSH_IP, or SSH_TAILSCALE_DNS_DROPLET (or *_DROPLET aliases) in ${ENV_FILE}" >&2
  exit 1
fi
if [[ -z "${SSH_USER:-}" ]]; then
  echo "ssh_droplet_user.sh: set SSH_USER or SSH_USER_DROPLET in ${ENV_FILE}" >&2
  exit 1
fi

LOGIN_TARGET="${_LOGIN_USER:-${AGENT_DROPLET_RUNTIME_USER:-hermesuser}}"
LU=$(printf '%q' "$LOGIN_TARGET")

REMOTE_BASE=(
  ssh -t -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none
  -o AddKeysToAgent=no -o ControlMaster=no -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4
  -i "$KEY_FILE" -p "${SSH_PORT}"
  "${SSH_USER}@${HOST}"
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
  _INNER="exec bash -l"
  if _droplet_venv_user_matches "$LOGIN_TARGET"; then
    _INNER=$(_droplet_wrap_cmd_with_venv "$_INNER")
  fi
  exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "sudo -u ${LU} -H bash -lc $(printf '%q' "$_INNER")"
fi

_USER_CMD="$*"
if _droplet_venv_user_matches "$LOGIN_TARGET"; then
  _USER_CMD=$(_droplet_wrap_cmd_with_venv "$_USER_CMD")
fi
INNER=$(printf '%q' "$_USER_CMD")
exec "${_DROPLET_ENV[@]}" "${REMOTE[@]}" "sudo -u ${LU} -H bash -lc ${INNER}"
