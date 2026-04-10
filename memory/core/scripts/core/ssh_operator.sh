#!/usr/bin/env bash
# SSH to the Mac mini as MACMINI_SSH_USER (operator) — Tailscale-hardened SSH (see macmini_* scripts).
#
# Credentials: HERMES_OPERATOR_ENV or ~/.env/.env (same file as droplet is fine):
#   MACMINI_SSH_USER (default operator), MACMINI_SSH_HOST, MACMINI_SSH_PORT (default 52822),
#   optional MACMINI_SSH_KEY (else SSH_KEY_FILE or ~/.env/.ssh_key)
#   optional HERMES_OPERATOR_REPO — absolute path on the mini (e.g. /Users/operator/hermes-agent)
#   optional HERMES_OPERATOR_ALLOW_ENV_PASSPHRASE or HERMES_DROPLET_ALLOW_ENV_PASSPHRASE + SSH_PASSPHRASE
#   for encrypted keys without TTY (shared ~/.env)
#
# HERMES_OPERATOR_WORKSTATION_CLI=1 (set by `hermes … operator`): do not use env-file SSH_PASSPHRASE /
# ASKPASS — type the key passphrase at the prompt (same pattern as ssh_droplet.sh).
#
# Sudo: no **sudo -S** / env password (unlike ssh_droplet). Remote **bash -lc** often has stdin on a
# pipe — sudo cannot read a password. We **reattach to /dev/tty** (same pattern as ssh_droplet after
# sudo -S), then **sudo -k** and **sudo -v** so this session must authenticate (unless sudoers has
# NOPASSWD — fix on the mini). **sudo -v** runs only when stdin is a TTY or **HERMES_OPERATOR_INTERACTIVE=1**
# (e.g. **hermes … operator**); set **HERMES_OPERATOR_SKIP_SUDO_VERIFY=1** for unattended automation.
# Opt out: **HERMES_OPERATOR_SSH_NO_TTY=1**, **HERMES_OPERATOR_SKIP_SUDO_K=1**, **HERMES_OPERATOR_REQUIRE_SUDO_VERIFY=0**.
#
# Usage:
#   ./ssh_operator.sh
#   ./ssh_operator.sh 'hostname'
#
set -euo pipefail

ENV_FILE="${HERMES_OPERATOR_ENV:-${HERMES_DROPLET_ENV:-${HOME}/.env/.env}}"
_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=operator_remote_venv.sh
source "${_SCRIPTS_DIR}/operator_remote_venv.sh"

KEY_FILE="${MACMINI_SSH_KEY:-${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}}"
MACMINI_USER=""
MACMINI_HOST=""
MACMINI_PORT="52822"
HERMES_OPERATOR_REPO_REMOTE=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_operator.sh: missing env file ${ENV_FILE} (set HERMES_OPERATOR_ENV)" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_operator.sh: missing key ${KEY_FILE} (set MACMINI_SSH_KEY or SSH_KEY_FILE)" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    MACMINI_SSH_USER) MACMINI_USER="${val}" ;;
    MACMINI_SSH_HOST) MACMINI_HOST="${val}" ;;
    SSH_IP_OPERATOR)
      [[ "$val" != *"@"* ]] && MACMINI_HOST="${val}"
      ;;
    MACMINI_SSH_PORT) MACMINI_PORT="${val}" ;;
    MACMINI_SSH_KEY) KEY_FILE="${val}" ;;
    HERMES_OPERATOR_REPO) HERMES_OPERATOR_REPO_REMOTE="${val}" ;;
    HERMES_OPERATOR_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    # Same shared ~/.env as droplet — unlock encrypted key for non-interactive SSH
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done <"$ENV_FILE"

MACMINI_USER="${MACMINI_USER:-operator}"
[[ -n "$MACMINI_HOST" ]] || {
  echo "ssh_operator.sh: set MACMINI_SSH_HOST (or SSH_IP_OPERATOR) in ${ENV_FILE}" >&2
  exit 1
}

if [[ "${HERMES_OPERATOR_WORKSTATION_CLI:-0}" == "1" ]]; then
  _ALLOW_ENV_PASS_FROM_FILE=0
  _RAW_SSH_PASSPHRASE=""
fi

_op_cleanup() {
  [[ -n "${_OP_PASSFILE:-}" && -f "$_OP_PASSFILE" ]] && rm -f "$_OP_PASSFILE"
  [[ -n "${_OP_ASKPASS_SCRIPT:-}" && -f "$_OP_ASKPASS_SCRIPT" ]] && rm -f "$_OP_ASKPASS_SCRIPT"
}
trap _op_cleanup EXIT

_SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _OP_PASSFILE=$(mktemp)
  _OP_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_OP_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" >"$_OP_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_OP_PASSFILE'" >"$_OP_ASKPASS_SCRIPT"
  chmod 700 "$_OP_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_OP_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

unset SSH_PASSPHRASE 2>/dev/null || true

# Default: always force a PTY so remote sudo(8) can prompt; ssh -T breaks password prompts.
_USE_TT=1
if [[ "${HERMES_OPERATOR_SSH_NO_TTY:-0}" == "1" ]]; then
  _USE_TT=0
fi

_SSH_FLAGS=(
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout="${HERMES_OPERATOR_SSH_CONNECT_TIMEOUT:-30}"
  -o ServerAliveInterval=10
  -o ServerAliveCountMax=30
  -o TCPKeepAlive=yes
  -i "$KEY_FILE"
  -p "${MACMINI_PORT:?}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  _SSH_FLAGS+=(-o UseKeychain=no)
fi
if [[ "$_USE_TT" == "1" ]]; then
  _SSH_FLAGS+=(-o RequestTTY=force)
  _SSH_BASE=(ssh -tt "${_SSH_FLAGS[@]}" "${MACMINI_USER}@${MACMINI_HOST}")
else
  _SSH_BASE=(ssh -T "${_SSH_FLAGS[@]}" "${MACMINI_USER}@${MACMINI_HOST}")
fi

_run_remote() {
  local remote_bash_cmd="$1"
  local pre=""
  # Reattach fds to the SSH PTY so sudo can prompt (bash -lc alone often leaves stdin non-tty).
  if [[ "$_USE_TT" == "1" ]]; then
    pre="exec >/dev/tty 2>&1; exec </dev/tty 2>/dev/null || true; "
  fi
  if [[ "${HERMES_OPERATOR_SKIP_SUDO_K:-0}" != "1" ]]; then
    pre+="sudo -k 2>/dev/null || true; "
  fi
  # Force an authentication check (prompts for password when needed). Skip for unattended runs.
  if [[ "${HERMES_OPERATOR_REQUIRE_SUDO_VERIFY:-1}" != "0" ]] && [[ "${HERMES_OPERATOR_SKIP_SUDO_VERIFY:-0}" != "1" ]]; then
    if [[ -t 0 ]] || [[ "${HERMES_OPERATOR_INTERACTIVE:-0}" == "1" ]]; then
      pre+="sudo -v || exit 1; "
    fi
  fi
  remote_bash_cmd="${pre}${remote_bash_cmd}"
  "${_SSH_ENV[@]}" "${_SSH_BASE[@]}" "bash -lc $(printf '%q' "$remote_bash_cmd")"
}

_REPO_EXPORT=""
if [[ -n "$HERMES_OPERATOR_REPO_REMOTE" ]]; then
  _rq=$(printf '%q' "$HERMES_OPERATOR_REPO_REMOTE")
  _REPO_EXPORT="export HERMES_OPERATOR_REPO=${_rq}; "
fi

if [[ $# -eq 0 ]]; then
  _INNER="${_REPO_EXPORT}$(_operator_interactive_shell_cmd)"
  _run_remote "$_INNER"
  exit $?
fi

_USER_CMD="$*"
_USER_CMD="${_REPO_EXPORT}$(_operator_wrap_cmd_with_venv "$_USER_CMD")"
_run_remote "$_USER_CMD"
