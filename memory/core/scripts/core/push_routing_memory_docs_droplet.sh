#!/usr/bin/env bash
# Upload routing reference docs tarball via scp (admin), then unpack into profile workspace as hermesuser.
# Piping a payload through droplet_run/ssh_droplet breaks: sudo -S + ssh -tt competes for stdin.
#
# Env: same ~/.env/.env as ssh_droplet.sh / droplet_run.sh (HERMES_DROPLET_ENV optional).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
_SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
_MEM_SCRIPTS="$(cd "$REPO_ROOT/memory/core/scripts/core" && pwd)"
# shellcheck source=../../memory/core/scripts/core/droplet_remote_venv.sh
source "${_MEM_SCRIPTS}/droplet_remote_venv.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

SSH_SUDO_PASSWORD=""
_ALLOW_ENV_PASS_FROM_FILE=0
_RAW_SSH_PASSPHRASE=""
_drop_cleanup() {
  [[ -n "${_DROPLET_PASSFILE:-}" && -f "$_DROPLET_PASSFILE" ]] && rm -f "$_DROPLET_PASSFILE"
  [[ -n "${_DROPLET_ASKPASS_SCRIPT:-}" && -f "$_DROPLET_ASKPASS_SCRIPT" ]] && rm -f "$_DROPLET_ASKPASS_SCRIPT"
  [[ -n "${_TMP_TGZ:-}" && -f "$_TMP_TGZ" ]] && rm -f "$_TMP_TGZ"
}
trap _drop_cleanup EXIT

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
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP|\
    SSH_PORT_DROPLET|SSH_USER_DROPLET|SSH_TAILSCALE_IP_DROPLET|SSH_IP_DROPLET|SSH_TAILSCALE_DNS_DROPLET)
      export "${key}=${val}"
      ;;
    SSH_KEY_FILE|SSH_KEY_DROPLET)
      export SSH_KEY_FILE="${val}"
      ;;
    SSH_SUDO_PASSWORD) SSH_SUDO_PASSWORD="${val}" ;;
    HERMES_DROPLET_ALLOW_ENV_PASSPHRASE)
      case "$val" in 1|true|TRUE|True|yes|YES) _ALLOW_ENV_PASS_FROM_FILE=1 ;; esac
      ;;
    SSH_PASSPHRASE) _RAW_SSH_PASSPHRASE="${val}" ;;
  esac
done <"$ENV_FILE"

KEY_FILE="$(droplet_resolve_ssh_key_file)" || exit 1
[[ -z "${SSH_TAILSCALE_IP:-}" && -n "${SSH_TAILSCALE_IP_DROPLET:-}" ]] && export SSH_TAILSCALE_IP="${SSH_TAILSCALE_IP_DROPLET}"
[[ -z "${SSH_IP:-}" && -n "${SSH_IP_DROPLET:-}" ]] && export SSH_IP="${SSH_IP_DROPLET}"
[[ -z "${SSH_USER:-}" && -n "${SSH_USER_DROPLET:-}" ]] && export SSH_USER="${SSH_USER_DROPLET}"
[[ -z "${SSH_PORT:-}" && -n "${SSH_PORT_DROPLET:-}" ]] && export SSH_PORT="${SSH_PORT_DROPLET}"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:-${SSH_TAILSCALE_DNS_DROPLET:-}}}"
[[ -n "$HOST" && -n "${SSH_USER:-}" ]] || {
  echo "set SSH_USER and SSH_TAILSCALE_IP / SSH_IP in ${ENV_FILE}" >&2
  exit 1
}
SSH_PORT="${SSH_PORT:-40227}"
[[ -n "$SSH_SUDO_PASSWORD" ]] || {
  echo "SSH_SUDO_PASSWORD required in ${ENV_FILE} for sudo to hermesuser" >&2
  exit 1
}

SRC_ROUTING="$REPO_ROOT/memory/knowledge/references/routing"
SRC_MANIFEST="$REPO_ROOT/memory/knowledge/references/ROUTING_DOCS.md"
[[ -d "$SRC_ROUTING" && -f "$SRC_MANIFEST" ]] || {
  echo "missing $SRC_ROUTING or $SRC_MANIFEST" >&2
  exit 1
}

_TMP_TGZ=$(mktemp)
tar czf "$_TMP_TGZ" -C "$REPO_ROOT" \
  memory/knowledge/references/routing \
  memory/knowledge/references/ROUTING_DOCS.md

REMOTE_TGZ=/tmp/hermes-routing-memory-sync.tgz
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

_SCP_FLAGS=(
  -o BatchMode=no
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o AddKeysToAgent=no
  -o ControlMaster=no
  -o ControlPath=none
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout="${HERMES_DROPLET_SSH_CONNECT_TIMEOUT:-30}"
  -i "$KEY_FILE"
  -P "$SSH_PORT"
)
if [[ "$(uname -s)" == "Darwin" ]]; then
  _SCP_FLAGS+=(-o UseKeychain=no)
fi

echo "scp -> ${SSH_USER}@${HOST}:${REMOTE_TGZ}"
"${_SSH_ENV[@]}" scp "${_SCP_FLAGS[@]}" "$_TMP_TGZ" "${SSH_USER}@${HOST}:${REMOTE_TGZ}"

echo "chmod a+r (admin) so hermesuser can read tarball…"
HERMES_DROPLET_ENV="$ENV_FILE" "$_MEM_SCRIPTS/droplet_run.sh" "chmod a+r ${REMOTE_TGZ}"

_UNPACK='set -e
cd /tmp
tar xzf '"$REMOTE_TGZ"'
ls -la memory/knowledge/references/routing/
for p in chief-orchestrator chief-orchestrator-droplet; do
  H="$HOME/.hermes/profiles/$p"
  if [[ -d "$H" ]]; then
    install -d "$H/workspace/memory/knowledge/references/routing"
    rsync -a --delete /tmp/memory/knowledge/references/routing/ "$H/workspace/memory/knowledge/references/routing/"
    cp -f /tmp/memory/knowledge/references/ROUTING_DOCS.md "$H/workspace/memory/knowledge/references/"
    echo "synced $p"
  fi
done
rm -rf /tmp/memory
'

echo "unpack as hermesuser (droplet_run)…"
HERMES_DROPLET_ENV="$ENV_FILE" "$_MEM_SCRIPTS/droplet_run.sh" --droplet-require-sudo --sudo-user hermesuser "$_UNPACK"

echo "remove ${REMOTE_TGZ} on server (admin)…"
HERMES_DROPLET_ENV="$ENV_FILE" "$_MEM_SCRIPTS/droplet_run.sh" "rm -f ${REMOTE_TGZ}"

echo "done."
