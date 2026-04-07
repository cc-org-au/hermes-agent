#!/usr/bin/env bash
# Rsync local_models/hub/ to the droplet hermes-agent checkout (not ~/.hermes).
# Uses the same ~/.env/.env as scripts/core/ssh_droplet.sh (SSH_*, key file).
#
# If SSH_USER is hermesadmin but the repo is owned by hermesuser, create the target
# directory once (e.g. sudo -u hermesuser mkdir -p) or SSH as hermesuser.
#
# Usage:
#   ./scripts/local_models/sync_to_droplet.sh
#   REMOTE_REPO=/home/hermesuser/hermes-agent ./scripts/local_models/sync_to_droplet.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${HERMES_DROPLET_ENV:-${HOME}/.env/.env}"
KEY_FILE="${SSH_KEY_FILE:-${HOME}/.env/.ssh_key}"
LOCAL_HUB="${ROOT}/local_models/hub"
REMOTE_REPO="${REMOTE_REPO:-/home/hermesuser/hermes-agent}"
REMOTE_HUB="${REMOTE_REPO}/local_models/hub"

if [[ ! -d "$LOCAL_HUB" ]]; then
  echo "sync_to_droplet.sh: missing ${LOCAL_HUB} (run download_models.py first)" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]] || [[ ! -f "$KEY_FILE" ]]; then
  echo "sync_to_droplet.sh: need ${ENV_FILE} and ${KEY_FILE}" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SSH_PORT|SSH_USER|SSH_TAILSCALE_IP|SSH_IP) export "${key}=${val}" ;;
  esac
done < "$ENV_FILE"

HOST="${SSH_TAILSCALE_IP:-${SSH_IP:?}}"
REMOTE_USER="${SSH_USER:?}"
PORT="${SSH_PORT:?}"

RSYNC_RSH="ssh -p ${PORT} -o BatchMode=no -o IdentitiesOnly=yes -o IdentityAgent=none -o AddKeysToAgent=no -o StrictHostKeyChecking=accept-new -i ${KEY_FILE}"
if [[ "$(uname -s)" == "Darwin" ]]; then
  RSYNC_RSH="${RSYNC_RSH} -o UseKeychain=no"
fi

echo "rsync ${LOCAL_HUB}/ -> ${REMOTE_USER}@${HOST}:${REMOTE_HUB}/"
rsync -avz --partial --append-verify \
  -e "${RSYNC_RSH}" \
  "${LOCAL_HUB}/" "${REMOTE_USER}@${HOST}:${REMOTE_HUB}/"

echo "Done. Set HERMES_LOCAL_INFERENCE_BASE_URL on the VPS to your vLLM/TGI OpenAI base (e.g. http://127.0.0.1:8000/v1)."
