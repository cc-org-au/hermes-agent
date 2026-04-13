#!/usr/bin/env bash
# Push routing reference docs into operator profile workspace over SSH (no repo git pull required).
# Uses stdin tarball decode on the mini; works with ssh_operator + HERMES_OPERATOR_SSH_NO_TTY=1.
#
# Env: HERMES_OPERATOR_ENV or ~/.env/.env (same as ssh_operator.sh).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${HERMES_OPERATOR_ENV:-${HOME}/.env/.env}"
SSH_OP="${REPO_ROOT}/hermes_cli/scripts/core/ssh_operator.sh"
[[ -x "$SSH_OP" || -f "$SSH_OP" ]] || {
  echo "missing $SSH_OP" >&2
  exit 1
}

SRC_ROUTING="$REPO_ROOT/memory/knowledge/references/routing"
SRC_MANIFEST="$REPO_ROOT/memory/knowledge/references/ROUTING_DOCS.md"
[[ -d "$SRC_ROUTING" && -f "$SRC_MANIFEST" ]] || {
  echo "missing routing pack under $REPO_ROOT/memory/knowledge/references/" >&2
  exit 1
}

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
tar czf "$TMP" -C "$REPO_ROOT" \
  memory/knowledge/references/routing \
  memory/knowledge/references/ROUTING_DOCS.md

_b64_pipe() {
  if command -v openssl >/dev/null 2>&1; then
    openssl base64 -A -in "$TMP"
  elif base64 --help 2>&1 | grep -q -- '-i'; then
    base64 -i "$TMP"
  else
    base64 <"$TMP" | tr -d '\n'
  fi
}

_REMOTE='base64 -d > /tmp/routing-memory-sync.tgz && cd /tmp && tar xzf routing-memory-sync.tgz && for p in chief-orchestrator chief-orchestrator-operator; do H="$HOME/.hermes/profiles/$p"; if [ -d "$H" ]; then install -d "$H/workspace/memory/knowledge/references/routing" && rsync -a --delete /tmp/memory/knowledge/references/routing/ "$H/workspace/memory/knowledge/references/routing/" && cp -f /tmp/memory/knowledge/references/ROUTING_DOCS.md "$H/workspace/memory/knowledge/references/" && echo "synced $p"; fi; done; rm -rf /tmp/memory /tmp/routing-memory-sync.tgz'

_b64_pipe | HERMES_OPERATOR_ENV="$ENV_FILE" HERMES_OPERATOR_SSH_NO_TTY=1 "$SSH_OP" "$_REMOTE"
echo "done."
