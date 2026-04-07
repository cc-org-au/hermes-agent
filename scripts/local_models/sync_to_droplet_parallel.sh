#!/usr/bin/env bash
# Parallel rsync of local_models/hub model trees to the droplet (one rsync per repo).
# Uses ~/.env/.env (SSH_*, optional SSH_PASSPHRASE, SSH_SUDO_PASSWORD for finalize) and
# ~/.env/.ssh_key — same family as memory/core/scripts/core/ssh_droplet.sh.
#
# Default path is hermesuser's hub. SSH_USER is usually hermesadmin, which cannot write there,
# so we rsync to an admin staging dir then sudo mv into hermesuser (same filesystem — no double disk).
#
# Headless: HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 + SSH_PASSPHRASE in ~/.env/.env (see ssh_droplet.sh).
# OpenSSH only runs SSH_ASKPASS when BatchMode=no (do not set BatchMode=yes for passphrase keys).
#
# Preflight: compares local hub size (du) to free space on the droplet root filesystem unless
# HERMES_SYNC_IGNORE_REMOTE_DF=1.
#
# Usage:
#   ./scripts/local_models/sync_to_droplet_parallel.sh
#   HERMES_SYNC_MAX_JOBS=8 ./scripts/local_models/sync_to_droplet_parallel.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
LOCAL_HUB="${REPO_ROOT}/local_models/hub"
REMOTE_REPO="${REMOTE_REPO:-/home/hermesuser/hermes-agent}"
REMOTE_HUB="${REMOTE_REPO}/local_models/hub"
REMOTE_STAGE="${HERMES_SYNC_REMOTE_STAGE:-/home/hermesadmin/hermes-local-hub-stage}"
REMOTE_RUNTIME_USER="${HERMES_SYNC_REMOTE_RUNTIME_USER:-hermesuser}"
LOG_DIR="${REPO_ROOT}/local_models/logs"
MAX_JOBS="${HERMES_SYNC_MAX_JOBS:-16}"

_drop_sync_cleanup() {
  [[ -n "${_SYNC_PASSFILE:-}" && -f "$_SYNC_PASSFILE" ]] && rm -f "$_SYNC_PASSFILE"
  [[ -n "${_SYNC_ASKPASS_SCRIPT:-}" && -f "$_SYNC_ASKPASS_SCRIPT" ]] && rm -f "$_SYNC_ASKPASS_SCRIPT"
}
trap _drop_sync_cleanup EXIT

mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
MAIN_LOG="${LOG_DIR}/sync_droplet_parallel_${STAMP}.log"

exec >>"$MAIN_LOG" 2>&1
echo "=== sync_to_droplet_parallel start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "REPO_ROOT=$REPO_ROOT LOCAL_HUB=$LOCAL_HUB"
echo "REMOTE_HUB (final)=${REMOTE_HUB}/"
echo "REMOTE_STAGE (rsync target)=${REMOTE_STAGE}/"

if [[ ! -d "$LOCAL_HUB" ]]; then
  echo "error: missing $LOCAL_HUB" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]] || [[ ! -f "$KEY_FILE" ]]; then
  echo "error: need $ENV_FILE and $KEY_FILE" >&2
  exit 1
fi

_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""
_SSH_SUDO_PASSWORD=""
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP) export "${key}=${val}" ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
    SSH_SUDO_PASSWORD) _SSH_SUDO_PASSWORD="${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
REMOTE_USER="${SSH_USER:?}"
PORT="${SSH_PORT:?}"

unset SSH_PASSPHRASE 2>/dev/null || true
unset SSH_AUTH_SOCK SSH_AUTH_SOCK_PRIVATE 2>/dev/null || true
SSH_BATCHMODE="no"
if [[ "$_ALLOW_ENV_PASS_FROM_FILE" == "1" ]]; then
  if [[ -z "${_RAW_SSH_PASSPHRASE}" ]]; then
    echo "error: HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1 in ${ENV_FILE} but SSH_PASSPHRASE missing (headless rsync needs it)." >&2
    exit 1
  fi
  _SYNC_PASSFILE=$(mktemp)
  _SYNC_ASKPASS_SCRIPT=$(mktemp)
  chmod 600 "$_SYNC_PASSFILE"
  printf '%s' "$_RAW_SSH_PASSPHRASE" > "$_SYNC_PASSFILE"
  printf '%s\n' '#!/bin/sh' "exec cat '$_SYNC_PASSFILE'" > "$_SYNC_ASKPASS_SCRIPT"
  chmod 700 "$_SYNC_ASKPASS_SCRIPT"
  export SSH_ASKPASS="$_SYNC_ASKPASS_SCRIPT"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
  SSH_BATCHMODE="no"
elif [[ -t 0 ]]; then
  SSH_BATCHMODE="no"
else
  SSH_BATCHMODE="yes"
fi

RSYNC_RSH="ssh -p ${PORT} -o BatchMode=${SSH_BATCHMODE} -o IdentitiesOnly=yes -o IdentityAgent=none"
RSYNC_RSH="${RSYNC_RSH} -o AddKeysToAgent=no -o ControlMaster=no -o ControlPath=none"
RSYNC_RSH="${RSYNC_RSH} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
RSYNC_RSH="${RSYNC_RSH} -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
RSYNC_RSH="${RSYNC_RSH} -i ${KEY_FILE}"
if [[ "$(uname -s)" == "Darwin" ]]; then
  RSYNC_RSH="${RSYNC_RSH} -o UseKeychain=no"
fi

_ssh() {
  eval "$RSYNC_RSH" "${REMOTE_USER}@${HOST}" "$@"
}

# Model directory basenames from hub/state.json (only recorded completed repos).
MODEL_DIRS=()
while IFS= read -r d; do
  [[ -n "$d" ]] && MODEL_DIRS+=("$d")
done < <(
  python3 - <<'PY' "$LOCAL_HUB"
import json, sys
from pathlib import Path
hub = Path(sys.argv[1])
state = hub / "state.json"
if not state.is_file():
    sys.exit(0)
data = json.loads(state.read_text())
for _repo, meta in (data.get("repos") or {}).items():
    p = Path(meta.get("path", ""))
    if p.is_dir() and p.parent.resolve() == hub.resolve():
        print(p.name)
PY
)

if [[ ${#MODEL_DIRS[@]} -eq 0 ]]; then
  echo "error: no model dirs found under $LOCAL_HUB (check state.json)" >&2
  exit 1
fi

echo "Model dirs (${#MODEL_DIRS[@]}): ${MODEL_DIRS[*]}"

_LOCAL_KB=$(du -sk "$LOCAL_HUB" | awk '{print $1}')
echo "Local hub size (du -sk): ${_LOCAL_KB} KiB"

if [[ "${HERMES_SYNC_IGNORE_REMOTE_DF:-}" != "1" ]]; then
  _REMOTE_LINE=$(_ssh "df -Pk / | tail -1" || true)
  _REMOTE_AVAIL_KB=$(echo "$_REMOTE_LINE" | awk '{print $4}')
  if [[ -z "${_REMOTE_AVAIL_KB:-}" || ! "$_REMOTE_AVAIL_KB" =~ ^[0-9]+$ ]]; then
    echo "warning: could not read remote df; set HERMES_SYNC_IGNORE_REMOTE_DF=1 to skip this check."
  else
    # Require ~5% headroom
    _NEED_KB=$((_LOCAL_KB + _LOCAL_KB / 20))
    if ((_REMOTE_AVAIL_KB < _NEED_KB)); then
      echo "error: droplet free space too small for this hub."
      echo "  local hub ~ ${_LOCAL_KB} KiB; remote / avail ${_REMOTE_AVAIL_KB} KiB (need ~ ${_NEED_KB} KiB with headroom)."
      echo "  Resize the VPS disk or remove models; then re-run. Or HERMES_SYNC_IGNORE_REMOTE_DF=1 to override (not recommended)."
      exit 1
    fi
    echo "Remote / avail (df): ${_REMOTE_AVAIL_KB} KiB — OK vs local ${_LOCAL_KB} KiB"
  fi
fi

# hermesadmin can only create the staging dir; hermesuser hub is created during sudo finalize.
_ssh "mkdir -p '${REMOTE_STAGE}'" || true

RSYNC_BASE=(rsync -av --partial --stats -e "$RSYNC_RSH")

echo ">>> state.json -> stage"
"${RSYNC_BASE[@]}" "${LOCAL_HUB}/state.json" "${REMOTE_USER}@${HOST}:${REMOTE_STAGE}/state.json"

job_n=0
for name in "${MODEL_DIRS[@]}"; do
  src="${LOCAL_HUB}/${name}/"
  if [[ ! -d "$src" ]]; then
    echo "skip missing: $src"
    continue
  fi
  while [[ "$(jobs -pr | wc -l | tr -d ' ')" -ge "$MAX_JOBS" ]]; do
    sleep 2
  done
  job_n=$((job_n + 1))
  echo ">>> [$job_n] background rsync ${name}/ -> stage"
  (
    set +e
    "${RSYNC_BASE[@]}" "${src}" "${REMOTE_USER}@${HOST}:${REMOTE_STAGE}/${name}/"
    ec=$?
    echo ">>> [$job_n] done ${name}/ exit=$ec"
    exit "$ec"
  ) &
done

wait

echo ">>> finalize: sudo mv from stage -> ${REMOTE_HUB}"
if [[ -z "${_SSH_SUDO_PASSWORD:-}" ]]; then
  echo "error: SSH_SUDO_PASSWORD missing from ${ENV_FILE}; cannot sudo mv into ${REMOTE_RUNTIME_USER} home." >&2
  echo "  Weights are under ${REMOTE_STAGE}/ on the droplet; fix sudo password in env and re-run this script (rsync is incremental)." >&2
  exit 1
fi

_PW_B64=$(printf '%s' "$_SSH_SUDO_PASSWORD" | base64 | tr -d '\n')
for name in "${MODEL_DIRS[@]}"; do
  if [[ ! -d "${LOCAL_HUB}/${name}" ]]; then
    continue
  fi
  echo ">>> sudo mv ${name}"
  eval "$RSYNC_RSH" "${REMOTE_USER}@${HOST}" \
    "printf '%s' '${_PW_B64}' | base64 -d | sudo -S bash -c \"set -e; mkdir -p '${REMOTE_HUB}'; rm -rf '${REMOTE_HUB}/${name}'; mv '${REMOTE_STAGE}/${name}' '${REMOTE_HUB}/'; chown -R ${REMOTE_RUNTIME_USER}:${REMOTE_RUNTIME_USER} '${REMOTE_HUB}/${name}'\""
done

eval "$RSYNC_RSH" "${REMOTE_USER}@${HOST}" \
  "printf '%s' '${_PW_B64}' | base64 -d | sudo -S bash -c \"set -e; mv -f '${REMOTE_STAGE}/state.json' '${REMOTE_HUB}/state.json' 2>/dev/null || true; chown ${REMOTE_RUNTIME_USER}:${REMOTE_RUNTIME_USER} '${REMOTE_HUB}/state.json' 2>/dev/null || true\""

echo "=== sync complete $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Optional: rm -rf ${REMOTE_STAGE} on the droplet to drop staging copies (final trees live under ${REMOTE_HUB})."
echo "Set HERMES_LOCAL_INFERENCE_BASE_URL on the VPS for vLLM/TGI when serving these weights."
echo "Main log: $MAIN_LOG"
