#!/usr/bin/env bash
# Replace local ~/.hermes with a tarball of /home/hermesuser/.hermes from the droplet.
#
# Uses ssh -T (no pseudo-tty) so the tar stream is not corrupted; ssh_droplet.sh uses -tt
# and must not be used for binary payloads.
#
# Requires the same ~/.env/.env as ssh_droplet.sh: SSH_*, key file, and SSH_SUDO_PASSWORD
# for remote sudo (hermesadmin reads hermesuser home via sudo tar).
#
# Usage:
#   ./scripts/core/droplet_pull_hermes_home.sh              # default: slim pull (see below)
#   ./scripts/core/droplet_pull_hermes_home.sh --full         # entire .hermes (large; live gateway may warn)
#   ./scripts/core/droplet_pull_hermes_home.sh --dry-run      # only show what would run
#
# Slim mode (default): skips heavy trees (logs, sessions, caches, WhatsApp bridge data,
# per-profile skills copies, sqlite session DB, etc.) but still pulls ``config.yaml``,
# ``.env`` files, ``workspace/memory/**``, ``workspace/policies/**``, and top-level
# ``policies/**``. Override defaults with:
#   HERMES_DROPLET_PULL_SLIM=0   # same as --full
#   HERMES_DROPLET_PULL_FULL=1   # same as --full
#
# Optional: after a successful extract, strip chat/messaging keys from every ``.env`` under
# ``~/.hermes`` (see strip_messaging_env_from_hermes_home.py). Set:
#   HERMES_PULL_STRIP_MESSAGING_ENV=1
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
DRY=0
FULL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --full) FULL=1; shift ;;
    --slim) FULL=0; shift ;;
    *)
      echo "droplet_pull_hermes_home.sh: unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SLIM=1
[[ "$FULL" == "1" ]] && SLIM=0
case "${HERMES_DROPLET_PULL_FULL:-0}" in 1|true|TRUE|yes|YES) SLIM=0 ;; esac
case "${HERMES_DROPLET_PULL_SLIM:-1}" in 0|false|FALSE|no|NO) SLIM=0 ;; esac

if [[ ! -f "$ENV_FILE" ]]; then
  echo "droplet_pull_hermes_home.sh: missing ${ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "$KEY_FILE" ]]; then
  echo "droplet_pull_hermes_home.sh: missing key ${KEY_FILE}" >&2
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

_drop_cleanup() {
  [[ -n "${_PULL_PASSFILE:-}" && -f "$_PULL_PASSFILE" ]] && rm -f "$_PULL_PASSFILE"
  [[ -n "${_PULL_ASKPASS_SCRIPT:-}" && -f "$_PULL_ASKPASS_SCRIPT" ]] && rm -f "$_PULL_ASKPASS_SCRIPT"
}
trap _drop_cleanup EXIT

_SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE)
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" && -n "${_RAW_SSH_PASSPHRASE}" ]]; then
  _PULL_PASSFILE=$(mktemp)
  _PULL_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_PULL_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_PULL_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_PULL_PASSFILE'" > "$_PULL_ASKPASS_SCRIPT"
  chmod 700 "$_PULL_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_PULL_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  _SSH_ENV=(env -u SSH_AUTH_SOCK -u SSH_AUTH_SOCK_PRIVATE)
fi

[[ -n "${SSH_SUDO_PASSWORD:-}" ]] || {
  echo "droplet_pull_hermes_home.sh: SSH_SUDO_PASSWORD must be set in ${ENV_FILE} for remote sudo tar." >&2
  exit 1
}

ARCHIVE="${TMPDIR:-/tmp}/hermes-home-from-droplet.$$".tar.gz
PW_B64=$(printf '%s' "$SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
# Live gateway may mutate files during archive; GNU tar otherwise exits 1 and breaks the SSH pipe.
# Slim excludes use --wildcards so patterns like .hermes/profiles/*/logs match; they intentionally
# avoid .hermes/profiles/*/workspace so workspace/memory and workspace/policies are included.
REMOTE_CMD="printf '%s' '${PW_B64}' | base64 -d | sudo -S tar czf - --warning=no-file-changed"
if [[ "$SLIM" == "1" ]]; then
  REMOTE_CMD+=" --wildcards --wildcards-match-slash"
  _slim_excludes=(
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
  for _ex in "${_slim_excludes[@]}"; do
    REMOTE_CMD+=" $(printf '%q' "$_ex")"
  done
fi
REMOTE_CMD+=" -C /home/hermesuser .hermes"

if [[ "$DRY" == "1" ]]; then
  echo "Would backup ${HOME}/.hermes then stream remote tar to ${ARCHIVE} and extract to ${HOME}"
  if [[ "$SLIM" == "1" ]]; then
    echo "(slim mode: heavy dirs excluded; workspace/memory and workspace/policies retained)"
  else
    echo "(full mode: entire .hermes)"
  fi
  exit 0
fi

echo "Streaming /home/hermesuser/.hermes from ${REMOTE_USER}@${HOST} ($([[ "$SLIM" == "1" ]] && echo slim || echo full)) ..."
if ! "${_SSH_ENV[@]}" "${SSH_BASE[@]}" "${REMOTE_USER}@${HOST}" "bash -lc $(printf '%q' "$REMOTE_CMD")" >"$ARCHIVE"; then
  echo "droplet_pull_hermes_home.sh: ssh/tar failed" >&2
  rm -f "$ARCHIVE"
  exit 1
fi

if [[ ! -s "$ARCHIVE" ]]; then
  echo "droplet_pull_hermes_home.sh: empty archive" >&2
  rm -f "$ARCHIVE"
  exit 1
fi

BACKUP="${HOME}/.hermes.backup.$(date +%Y%m%d%H%M%S)"
if [[ -d "${HOME}/.hermes" ]]; then
  echo "Moving ${HOME}/.hermes -> ${BACKUP}"
  mv "${HOME}/.hermes" "$BACKUP"
fi

echo "Extracting into ${HOME} ..."
tar xzf "$ARCHIVE" -C "${HOME}"
rm -f "$ARCHIVE"

chmod -R u+rwX "${HOME}/.hermes" 2>/dev/null || true

# Stale Linux gateway PID confuses local doctor/status.
rm -f "${HOME}/.hermes/gateway.pid" "${HOME}/.hermes/profiles/"*/gateway.pid 2>/dev/null || true

echo "Done. Previous tree (if any): ${BACKUP}"
echo "Do not run a second messaging gateway with the same bot tokens locally; use a different profile or stop the VPS gateway first."

if [[ "${HERMES_PULL_STRIP_MESSAGING_ENV:-0}" == "1" ]]; then
  _repo=""
  _d="$ROOT"
  while [[ "$_d" != "/" ]]; do
    if [[ -f "$_d/pyproject.toml" ]] || [[ -f "$_d/hermes_cli/main.py" ]]; then
      _repo="$_d"
      break
    fi
    _d="$(dirname "$_d")"
  done
  if [[ -n "$_repo" && -x "$_repo/venv/bin/python" ]]; then
    echo ">>> HERMES_PULL_STRIP_MESSAGING_ENV=1: stripping messaging keys from ${HOME}/.hermes/.env files ..."
    "$_repo/venv/bin/python" "$ROOT/strip_messaging_env_from_hermes_home.py" "${HOME}/.hermes"
  else
    echo "warning: could not find repo venv; run manually: python scripts/core/strip_messaging_env_from_hermes_home.py" >&2
  fi
fi
