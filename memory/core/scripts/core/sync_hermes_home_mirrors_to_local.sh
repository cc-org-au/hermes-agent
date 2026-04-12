#!/usr/bin/env bash
# Copy HERMES_HOME from the droplet and from the operator Mac mini to THIS machine
# (the workstation running this script — not the remotes), under separate roots:
#   ${HERMES_MIRROR_DROPLET:-$HOME/.hermes-droplet}/.hermes
#   ${HERMES_MIRROR_OPERATOR:-$HOME/.hermes-operator}/.hermes
#
# Use these as read-only mirrors / backups. Do not point a live gateway at them with
# production tokens unless you understand duplicate-session risks.
#
# Droplet pull: same SSH + sudo tar stream as droplet_pull_hermes_home.sh (slim by default).
#   Requires HERMES_DROPLET_ENV (default ~/.env/.env), SSH_KEY_FILE, SSH_SUDO_PASSWORD.
#
# Operator pull: rsync FROM mini TO local (reverse of rsync_hermes_home_to_operator.sh).
#   Uses rsync --delete so the local mirror matches the mini (extra local files under
#   ~/.hermes-operator/.hermes are removed).
#   Requires HERMES_OPERATOR_ENV, MACMINI_SSH_* from the same file as ssh_operator.sh.
#
# Usage:
#   ./scripts/core/sync_hermes_home_mirrors_to_local.sh
#   ./scripts/core/sync_hermes_home_mirrors_to_local.sh --droplet-only
#   ./scripts/core/sync_hermes_home_mirrors_to_local.sh --operator-only
#   ./scripts/core/sync_hermes_home_mirrors_to_local.sh --full    # droplet: full .hermes (large)
#   ./scripts/core/sync_hermes_home_mirrors_to_local.sh --dry-run
#
set -euo pipefail

DROP_ROOT="${HERMES_MIRROR_DROPLET:-${HOME}/.hermes-droplet}"
OP_ROOT="${HERMES_MIRROR_OPERATOR:-${HOME}/.hermes-operator}"
DO_DROPLET=1
DO_OPERATOR=1
DRY=0
FULL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --droplet-only) DO_OPERATOR=0; shift ;;
    --operator-only) DO_DROPLET=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --full) FULL=1; shift ;;
    --slim) FULL=0; shift ;;
    *)
      echo "sync_hermes_home_mirrors_to_local.sh: unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SLIM=1
[[ "$FULL" == "1" ]] && SLIM=0

if [[ "$DRY" == "1" ]]; then
  echo "Would sync droplet -> ${DROP_ROOT}/.hermes (slim=$SLIM) and operator -> ${OP_ROOT}/.hermes"
  exit 0
fi

_sync_droplet() {
  local envf="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
  local keyf="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
  if [[ ! -f "$envf" || ! -f "$keyf" ]]; then
    echo "sync: skipping droplet (missing ${envf} or ${keyf})" >&2
    return 0
  fi
  local SSH_SUDO_PASSWORD="" _ALLOW_ENV_PASS_FROM_FILE=0 _RAW_SSH_PASSPHRASE=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      SSH_PORT|SSH_PORT_DROPLET|SSH_USER|SSH_USER_DROPLET|SSH_TAILSCALE_IP|SSH_TAILSCALE_IP_DROPLET|\
SSH_IP|SSH_IP_DROPLET|SSH_TAILSCALE_DNS_DROPLET|SSH_SUDO_PASSWORD) export "${key}=${val}" ;;
      HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
        case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
        ;;
      SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
    esac
  done <"$envf"

  # Same *_DROPLET fallbacks as ssh_droplet.sh / droplet_pull_hermes_home.sh
  if [[ -z "${SSH_TAILSCALE_IP:-}" && -n "${SSH_TAILSCALE_IP_DROPLET:-}" ]]; then export SSH_TAILSCALE_IP="${SSH_TAILSCALE_IP_DROPLET}"; fi
  if [[ -z "${SSH_IP:-}" && -n "${SSH_IP_DROPLET:-}" ]]; then export SSH_IP="${SSH_IP_DROPLET}"; fi
  if [[ -z "${SSH_USER:-}" && -n "${SSH_USER_DROPLET:-}" ]]; then export SSH_USER="${SSH_USER_DROPLET}"; fi
  if [[ -z "${SSH_PORT:-}" && -n "${SSH_PORT_DROPLET:-}" ]]; then export SSH_PORT="${SSH_PORT_DROPLET}"; fi

  HOST="${SSH_TAILSCALE_IP:-${SSH_IP:-${SSH_TAILSCALE_DNS_DROPLET:-}}}"
  REMOTE_USER="${SSH_USER:-}"
  if [[ -z "$HOST" || -z "$REMOTE_USER" ]]; then
    echo "sync: skipping droplet (SSH_TAILSCALE_IP/SSH_IP or SSH_USER missing in ${envf})" >&2
    return 0
  fi
  SSH_PORT="${SSH_PORT:-40227}"
  [[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
    echo "sync: droplet mirror needs SSH_SUDO_PASSWORD in ${envf}" >&2
    return 1
  }

  local SSH_BASE=(
    ssh -T
    -o BatchMode=no
    -o IdentitiesOnly=yes
    -o IdentityAgent=none
    -o AddKeysToAgent=no
    -o ControlMaster=no
    -o ControlPath=none
    -o StrictHostKeyChecking=accept-new
    -o ConnectTimeout=30
    -i "$keyf"
    -p "${SSH_PORT}"
  )
  if [[ "$(uname -s)" == "Darwin" ]]; then
    SSH_BASE+=(-o UseKeychain=no)
  fi

  _drop_cleanup() {
    [[ -n "${_SYNC_PULL_PASSFILE:-}" && -f "$_SYNC_PULL_PASSFILE" ]] && rm -f "$_SYNC_PULL_PASSFILE"
    [[ -n "${_SYNC_PULL_ASKPASS_SCRIPT:-}" && -f "$_SYNC_PULL_ASKPASS_SCRIPT" ]] && rm -f "$_SYNC_PULL_ASKPASS_SCRIPT"
  }
  trap _drop_cleanup EXIT

  local _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
  if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
    _SYNC_PULL_PASSFILE=$(mktemp)
    _SYNC_PULL_ASKPASS_SCRIPT=$(mktemp)
    chmod 600 "$_SYNC_PULL_PASSFILE"
    printf '%s' "$_RAW_SSH_PASSPHRASE" >"$_SYNC_PULL_PASSFILE"
    printf '%s\n' '#!/bin/sh' "exec cat '$_SYNC_PULL_PASSFILE'" >"$_SYNC_PULL_ASKPASS_SCRIPT"
    chmod 700 "$_SYNC_PULL_ASKPASS_SCRIPT"
    export SSH_ASKPASS="$_SYNC_PULL_ASKPASS_SCRIPT"
    export SSH_ASKPASS_REQUIRE=force
    export DISPLAY="${DISPLAY:-:0}"
    _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
  fi

  local ARCHIVE="${TMPDIR:-/tmp}/hermes-mirror-droplet.$$".tar.gz
  local PW_B64
  PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
  local REMOTE_CMD="printf '%s' '${PW_B64}' | base64 -d | sudo -S tar czf - --warning=no-file-changed"
  if [[ "$SLIM" == "1" ]]; then
    REMOTE_CMD+=" --wildcards --wildcards-match-slash"
    local _slim_excludes=(
      '--exclude=.hermes/logs'
      '--exclude=.hermes/sessions'
      '--exclude=.hermes/cache'
      '--exclude=.hermes/whatsapp'
      '--exclude=.hermes/skills'
      '--exclude=.hermes/bin'
      '--exclude=.hermes/archive'
      '--exclude=.hermes/backups'
      '--exclude=.hermes/profiles/*/logs'
      '--exclude=.hermes/profiles/*/sessions'
      '--exclude=.hermes/profiles/*/cache'
      '--exclude=.hermes/profiles/*/skills'
      '--exclude=.hermes/profiles/*/whatsapp'
      '--exclude=.hermes/profiles/*/state.db'
      '--exclude=.hermes/profiles/*/models_dev_cache.json'
      '--exclude=*.log'
    )
    local _ex
    for _ex in "${_slim_excludes[@]}"; do
      REMOTE_CMD+=" $(printf '%q' "$_ex")"
    done
  fi
  REMOTE_CMD+=" -C /home/hermesuser .hermes"

  echo ">>> Droplet -> ${DROP_ROOT}/.hermes ($([[ "$SLIM" == "1" ]] && echo slim || echo full)) ..."
  if ! "${_SSH_ENV[@]}" "${SSH_BASE[@]}" "${REMOTE_USER}@${HOST}" "bash -lc $(printf '%q' "$REMOTE_CMD")" >"$ARCHIVE"; then
    echo "sync: droplet ssh/tar failed" >&2
    rm -f "$ARCHIVE"
    return 1
  fi
  [[ -s "$ARCHIVE" ]] || {
    echo "sync: droplet empty archive" >&2
    rm -f "$ARCHIVE"
    return 1
  }
  mkdir -p "${DROP_ROOT}"
  rm -rf "${DROP_ROOT}/.hermes"
  tar xzf "$ARCHIVE" -C "${DROP_ROOT}"
  rm -f "$ARCHIVE"
  chmod -R u+rwX "${DROP_ROOT}/.hermes" 2>/dev/null || true
  rm -f "${DROP_ROOT}/.hermes/gateway.pid" "${DROP_ROOT}/.hermes/profiles/"*/gateway.pid 2>/dev/null || true
  echo ">>> Droplet mirror done: ${DROP_ROOT}/.hermes"
}

_sync_operator() {
  local envf="${HERMES_OPERATOR_ENV:-${HERMES_DROPLET_ENV:-${HOME}/.env/.env}}"
  local keyf="${MACMINI_SSH_KEY:-${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}}"
  if [[ ! -f "$envf" || ! -f "$keyf" ]]; then
    echo "sync: skipping operator (missing ${envf} or ${keyf})" >&2
    return 0
  fi
  local MACMINI_USER="" MACMINI_HOST="" MACMINI_PORT="52822"
  local _ALLOW_ENV_PASS_FROM_FILE=0 _RAW_SSH_PASSPHRASE=""
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
      MACMINI_SSH_KEY) keyf="${val}" ;;
      HERMES_OPERATOR_ALLOW_ENV_PASSPHRASE|HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
        case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
        ;;
      SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
    esac
  done <"$envf"
  MACMINI_USER="${MACMINI_USER:-operator}"
  [[ -n "$MACMINI_HOST" ]] || {
    echo "sync: skipping operator (set MACMINI_SSH_HOST or SSH_IP_OPERATOR in ${envf})" >&2
    return 0
  }

  _op_cleanup() {
    [[ -n "${_S_OP_PASS:-}" && -f "$_S_OP_PASS" ]] && rm -f "$_S_OP_PASS"
    [[ -n "${_S_OP_ASK:-}" && -f "$_S_OP_ASK" ]] && rm -f "$_S_OP_ASK"
  }
  trap '_op_cleanup; rm -f "${_SYNC_OP_WRAP:-}"' EXIT

  local _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
  if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
    _S_OP_PASS=$(mktemp)
    _S_OP_ASK=$(mktemp)
    chmod 600 "$_S_OP_PASS"
    printf '%s' "$_RAW_SSH_PASSPHRASE" >"$_S_OP_PASS"
    printf '%s\n' '#!/bin/sh' "exec cat '$_S_OP_PASS'" >"$_S_OP_ASK"
    chmod 700 "$_S_OP_ASK"
    export SSH_ASKPASS="$_S_OP_ASK"
    export SSH_ASKPASS_REQUIRE=force
    export DISPLAY="${DISPLAY:-:0}"
    _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
  fi

  local _SSH_FLAGS=(
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
    -i "$keyf"
    -p "${MACMINI_PORT}"
  )
  if [[ "$(uname -s)" == "Darwin" ]]; then
    _SSH_FLAGS+=(-o UseKeychain=no)
  fi

  _SYNC_OP_WRAP=$(mktemp)
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'exec '
    printf '%q ' "${_SSH_ENV[@]}"
    printf '%q ' ssh -T
    printf '%q ' "${_SSH_FLAGS[@]}"
    echo '"$@"'
  } >"$_SYNC_OP_WRAP"
  chmod 700 "$_SYNC_OP_WRAP"

  mkdir -p "${OP_ROOT}/.hermes"
  echo ">>> Operator -> ${OP_ROOT}/.hermes (rsync) ..."
  rsync -avz --delete -e "$_SYNC_OP_WRAP" \
    "${MACMINI_USER}@${MACMINI_HOST}:.hermes/" "${OP_ROOT}/.hermes/"
  rm -f "${OP_ROOT}/.hermes/gateway.pid" "${OP_ROOT}/.hermes/profiles/"*/gateway.pid 2>/dev/null || true
  echo ">>> Operator mirror done: ${OP_ROOT}/.hermes"
}

if [[ "$DO_DROPLET" == "1" ]]; then
  (_sync_droplet) || exit $?
fi
if [[ "$DO_OPERATOR" == "1" ]]; then
  (_sync_operator) || exit $?
fi
echo "All requested mirrors finished."
