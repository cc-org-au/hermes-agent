#!/usr/bin/env bash
# SSH to the Mac mini as MACMINI_SSH_USER (operator) — Tailscale-hardened SSH (see macmini_* scripts).
#
# Credentials: HERMES_OPERATOR_ENV or ~/.env/.env (same file as droplet is fine):
#   MACMINI_SSH_USER (default operator), MACMINI_SSH_HOST, MACMINI_SSH_PORT (default 52822),
#   optional MACMINI_SSH_KEY in the env file (else SSH_KEY_FILE or ~/.env/.ssh_key)
#   optional MACMINI_SSH_LAN_IP — when set (and differs from MACMINI_SSH_HOST), try LAN first by default
#     with HERMES_OPERATOR_SSH_PRIMARY_CONNECT_TIMEOUT (default 8s), then Tailscale with
#     HERMES_OPERATOR_SSH_CONNECT_TIMEOUT (default 30s). Set MACMINI_SSH_TRY_LAN_FIRST=0 for TS-first.
#   optional HERMES_OPERATOR_REPO — absolute path on the mini (e.g. /Users/operator/hermes-agent)
#   optional HERMES_OPERATOR_ALLOW_ENV_PASSPHRASE or HERMES_DROPLET_ALLOW_ENV_PASSPHRASE + SSH_PASSPHRASE
#   for encrypted keys without TTY (shared ~/.env)
#
# HERMES_OPERATOR_WORKSTATION_CLI=1 (set by `hermes … operator`): do not use env-file SSH_PASSPHRASE /
# ASKPASS — type the key passphrase at the prompt (same pattern as ssh_droplet.sh).
#
# Sudo: this script does **not** run **sudo** (no **sudo -S** / env password, unlike ssh_droplet). Optional
# **HERMES_OPERATOR_SSH_NO_TTY=1** uses **ssh -T** (no PTY).
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
_MACMINI_LAN_IP_READ=""
_TRY_LAN_FIRST_READ=""
_TRY_LAN_FIRST_IN_FILE=0

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ssh_operator.sh: missing env file ${ENV_FILE} (set HERMES_OPERATOR_ENV)" >&2
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
    MACMINI_SSH_LAN_IP) _MACMINI_LAN_IP_READ="${val}" ;;
    MACMINI_SSH_TRY_LAN_FIRST)
      _TRY_LAN_FIRST_READ="${val}"
      _TRY_LAN_FIRST_IN_FILE=1
      ;;
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
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ssh_operator.sh: missing key ${KEY_FILE} (set MACMINI_SSH_KEY in ${ENV_FILE} or export MACMINI_SSH_KEY / SSH_KEY_FILE)" >&2
  exit 1
fi

# Shell env wins over file (same pattern as ssh-operator-breakglass.sh).
MACMINI_SSH_LAN_IP="${MACMINI_SSH_LAN_IP:-${_MACMINI_LAN_IP_READ:-}}"
if [[ -n "${MACMINI_SSH_LAN_IP}" && "${MACMINI_SSH_LAN_IP}" != "${MACMINI_HOST}" && "${_TRY_LAN_FIRST_IN_FILE}" -eq 0 && -z "${MACMINI_SSH_TRY_LAN_FIRST+x}" ]]; then
  MACMINI_SSH_TRY_LAN_FIRST=1
fi

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

_USE_TT=1
if [[ "${HERMES_OPERATOR_SSH_NO_TTY:-0}" == "1" ]]; then
  _USE_TT=0
fi

CTO_FINAL="${HERMES_OPERATOR_SSH_CONNECT_TIMEOUT:-30}"
CTO_QUICK="${HERMES_OPERATOR_SSH_PRIMARY_CONNECT_TIMEOUT:-8}"

_SSH_FLAGS_COMMON=(
  -4
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ServerAliveInterval=10
  -o ServerAliveCountMax=30
  -o TCPKeepAlive=yes
  -i "$KEY_FILE"
  -p "${MACMINI_PORT:?}"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  _SSH_FLAGS_COMMON+=(-o UseKeychain=no)
fi

_op_build_ssh_base() {
  local target_host="$1"
  local cto="$2"
  local ssh_cmd=(ssh)
  if [[ "$_USE_TT" == "1" ]]; then
    ssh_cmd+=(-tt)
  else
    ssh_cmd+=(-T)
  fi
  ssh_cmd+=("${_SSH_FLAGS_COMMON[@]}" -o "ConnectTimeout=${cto}" "${MACMINI_USER}@${target_host}")
  _SSH_BASE=("${ssh_cmd[@]}")
}

_candidate_hosts=()
_op_add_candidate() {
  local cand="$1"
  [[ -z "$cand" ]] && return
  local x
  for x in "${_candidate_hosts[@]:-}"; do
    [[ "$x" == "$cand" ]] && return
  done
  _candidate_hosts+=("$cand")
}

_try_lan_first=0
case "${MACMINI_SSH_TRY_LAN_FIRST:-${_TRY_LAN_FIRST_READ:-0}}" in 1|true|TRUE|True|yes|YES) _try_lan_first=1 ;; esac
if [[ "$_try_lan_first" == "1" ]]; then
  _op_add_candidate "${MACMINI_SSH_LAN_IP:-}"
  _op_add_candidate "${MACMINI_HOST}"
else
  _op_add_candidate "${MACMINI_HOST}"
  _op_add_candidate "${MACMINI_SSH_LAN_IP:-}"
fi

_run_remote_with_base() {
  local remote_bash_cmd="$1"
  "${_SSH_ENV[@]}" "${_SSH_BASE[@]}" "bash -lc $(printf '%q' "$remote_bash_cmd")"
}

_REPO_EXPORT=""
if [[ -n "$HERMES_OPERATOR_REPO_REMOTE" ]]; then
  _rq=$(printf '%q' "$HERMES_OPERATOR_REPO_REMOTE")
  _REPO_EXPORT="export HERMES_OPERATOR_REPO=${_rq}; "
fi

if [[ $# -eq 0 ]]; then
  _INNER="${_REPO_EXPORT}$(_operator_interactive_shell_cmd)"
else
  _INNER="${_REPO_EXPORT}$(_operator_wrap_cmd_with_venv "$*")"
fi

_n="${#_candidate_hosts[@]}"
if [[ "$_n" -eq 0 ]]; then
  echo "ssh_operator.sh: no SSH target hosts (internal error)." >&2
  exit 1
fi

if [[ "$_n" -eq 1 ]]; then
  export HERMES_OPERATOR_SSH_DST="${MACMINI_USER}@${_candidate_hosts[0]}:${MACMINI_PORT}"
  _op_build_ssh_base "${_candidate_hosts[0]}" "$CTO_FINAL"
  _run_remote_with_base "$_INNER"
  exit $?
fi

last=255
for ((_i = 0; _i < _n; _i++)); do
  h="${_candidate_hosts[$_i]}"
  if [[ "$_n" -gt 1 && "$_i" -lt $((_n - 1)) ]]; then
    _cto="$CTO_QUICK"
  else
    _cto="$CTO_FINAL"
  fi
  if [[ "$_i" -gt 0 ]]; then
    echo "[ssh_operator] fallback: trying ${MACMINI_USER}@${h} port ${MACMINI_PORT} (ConnectTimeout=${_cto}s) ..." >&2
  elif [[ "${HERMES_OPERATOR_SSH_VERBOSE_TRY:-0}" == "1" ]]; then
    echo "[ssh_operator] trying ${MACMINI_USER}@${h} port ${MACMINI_PORT} (ConnectTimeout=${_cto}s) ..." >&2
  fi
  export HERMES_OPERATOR_SSH_DST="${MACMINI_USER}@${h}:${MACMINI_PORT}"
  _op_build_ssh_base "$h" "$_cto"
  if _run_remote_with_base "$_INNER"; then
    exit 0
  fi
  last=$?
done

echo "[ssh_operator] all targets failed (last exit ${last})." >&2
echo "  Laptop: tailscale status; tailscale ping <mini-ts-ip>" >&2
echo "  ~/.env/.env: set MACMINI_SSH_LAN_IP=<mini-LAN-IPv4> when home Wi‑Fi works but TS does not" >&2
echo "  Mini (Screen Sharing): sudo bash ~/hermes-agent/memory/core/scripts/core/operator_mini_install_ssh_lan_resilience.sh" >&2
exit "$last"
