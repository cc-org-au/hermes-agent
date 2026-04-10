#!/usr/bin/env bash
# Push workstation HERMES_HOME to the Mac mini operator account (~/.hermes), using the same
# ~/.env/.env layout as ssh_operator.sh (MACMINI_*, SSH_PASSPHRASE + HERMES_DROPLET_ALLOW_ENV_PASSPHRASE).
#
# Usage:
#   ./rsync_hermes_home_to_operator.sh
#   ./rsync_hermes_home_to_operator.sh --dry-run
#   ./rsync_hermes_home_to_operator.sh --remove-in-repo-copy   # rm -rf ~/hermes-agent/.hermes on mini
#
set -euo pipefail

ENV_FILE="${HERMES_OPERATOR_ENV:-${HERMES_DROPLET_ENV:-${HOME}/.env/.env}}"
KEY_FILE="${MACMINI_SSH_KEY:-${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}}"
DRY_RUN=()
REMOVE_REPO=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=(--dry-run) ;;
    --remove-in-repo-copy) REMOVE_REPO=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

MACMINI_USER=""
MACMINI_HOST=""
MACMINI_PORT="52822"
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""

if [[ ! -f "$ENV_FILE" ]]; then
  echo "rsync_hermes_home_to_operator.sh: missing env file ${ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "rsync_hermes_home_to_operator.sh: missing key ${KEY_FILE}" >&2
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
    HERMES_OPERATOR_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done <"$ENV_FILE"

MACMINI_USER="${MACMINI_USER:-operator}"
[[ -n "$MACMINI_HOST" ]] || {
  echo "rsync_hermes_home_to_operator.sh: set MACMINI_SSH_HOST (or SSH_IP_OPERATOR) in ${ENV_FILE}" >&2
  exit 1
}

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

_SRC="${HERMES_HOME_RSYNC_SRC:-${HOME}/.hermes}"
[[ -d "$_SRC" ]] || {
  echo "rsync_hermes_home_to_operator.sh: missing source dir ${_SRC}" >&2
  exit 1
}

# rsync -e must be a single program name; use a temp wrapper to preserve array + env.
_WRAPPER=$(mktemp)
trap '_op_cleanup; rm -f "${_WRAPPER:-}"' EXIT
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  printf 'exec '
  printf '%q ' "${_SSH_ENV[@]}"
  printf '%q ' ssh -T
  printf '%q ' "${_SSH_FLAGS[@]}"
  echo '"$@"'
} >"$_WRAPPER"
chmod 700 "$_WRAPPER"

echo "rsync: ${_SRC}/ -> ${MACMINI_USER}@${MACMINI_HOST}:.hermes/"
# Bash 3.2 + set -u: "${empty[@]}" can error — branch on dry-run
if [[ ${#DRY_RUN[@]} -gt 0 ]]; then
  rsync -avz "${DRY_RUN[@]}" -e "$_WRAPPER" "${_SRC}/" "${MACMINI_USER}@${MACMINI_HOST}:.hermes/"
else
  rsync -avz -e "$_WRAPPER" "${_SRC}/" "${MACMINI_USER}@${MACMINI_HOST}:.hermes/"
fi

if [[ "$REMOVE_REPO" == "1" && ${#DRY_RUN[@]} -eq 0 ]]; then
  echo "Removing ~/hermes-agent/.hermes on mini (if present)…"
  "${_WRAPPER}" "${MACMINI_USER}@${MACMINI_HOST}" "rm -rf \"\$HOME/hermes-agent/.hermes\" 2>/dev/null; echo done"
fi
