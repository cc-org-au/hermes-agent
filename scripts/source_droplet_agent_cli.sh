#!/usr/bin/env bash
# Droplet (VPS) CLI proxies — source this file; do not execute.
#
# When AGENT_DROPLET_ENABLE=1 or AGENT_VPS_PATH=1, defines:
#   ${AGENT_CLI_NAME}-droplet   — forwards all arguments to the same CLI entrypoint on the VPS
#   ${AGENT_CLI_NAME}-<verb>-droplet — aliases for common verbs (tui, setup, gateway, doctor)
#
# Requires ~/.env/.env (or AGENT_DROPLET_ENV) with SSH_* and SSH_SUDO_PASSWORD like ssh_droplet.sh,
# and scripts/ssh_droplet.sh in this repository.
#
# Override defaults with env vars:
#   AGENT_CLI_NAME              default: hermes
#   AGENT_DROPLET_RUNTIME_USER  default: hermesuser  (argument to ssh_droplet.sh --sudo-user)
#   AGENT_DROPLET_RUNTIME_HOME  default: /home/hermesuser/.hermes
#   AGENT_DROPLET_REPO          default: /home/hermesuser/hermes-agent

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "source_droplet_agent_cli: source this file, do not execute" >&2
  exit 1
fi

if [[ "${AGENT_DROPLET_ENABLE:-}" != "1" && "${AGENT_VPS_PATH:-}" != "1" ]]; then
  return 0 2>/dev/null || exit 0
fi

_ENV_FILE="${AGENT_DROPLET_ENV:-${HOME}/.env/.env}"
if [[ ! -f "$_ENV_FILE" ]]; then
  echo "source_droplet_agent_cli: missing ${_ENV_FILE} (set AGENT_DROPLET_ENV or create file)" >&2
  return 0 2>/dev/null || exit 0
fi

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"
_SSH_DROPLET="${_REPO_ROOT}/scripts/ssh_droplet.sh"
if [[ ! -x "$_SSH_DROPLET" && ! -f "$_SSH_DROPLET" ]]; then
  echo "source_droplet_agent_cli: missing ${_SSH_DROPLET}" >&2
  return 0 2>/dev/null || exit 0
fi

AGENT_CLI_NAME="${AGENT_CLI_NAME:-hermes}"
AGENT_DROPLET_RUNTIME_USER="${AGENT_DROPLET_RUNTIME_USER:-hermesuser}"
AGENT_DROPLET_RUNTIME_HOME="${AGENT_DROPLET_RUNTIME_HOME:-/home/hermesuser/.hermes}"
AGENT_DROPLET_REPO="${AGENT_DROPLET_REPO:-/home/hermesuser/hermes-agent}"

_agent_droplet_forward() {
  local hh repo cmd a
  hh=$(printf '%q' "$AGENT_DROPLET_RUNTIME_HOME")
  repo=$(printf '%q' "$AGENT_DROPLET_REPO")
  cmd="export HERMES_HOME=${hh}; cd ${repo} && exec ./venv/bin/python -m hermes_cli.main"
  for a in "$@"; do
    cmd+=" $(printf '%q' "$a")"
  done
  bash "$_SSH_DROPLET" --sudo-user "$AGENT_DROPLET_RUNTIME_USER" "$cmd"
}

# Dynamic name: e.g. hermes-droplet when AGENT_CLI_NAME=hermes
eval "${AGENT_CLI_NAME}-droplet() { _agent_droplet_forward \"\$@\"; }"

# Suffixed convenience aliases (no extra arguments required; suffix is always -droplet)
eval "alias ${AGENT_CLI_NAME}-tui-droplet='${AGENT_CLI_NAME}-droplet tui'"
eval "alias ${AGENT_CLI_NAME}-setup-droplet='${AGENT_CLI_NAME}-droplet setup'"
eval "alias ${AGENT_CLI_NAME}-gateway-droplet='${AGENT_CLI_NAME}-droplet gateway'"
eval "alias ${AGENT_CLI_NAME}-doctor-droplet='${AGENT_CLI_NAME}-droplet doctor'"
eval "alias ${AGENT_CLI_NAME}-watchdog-check-droplet='${AGENT_CLI_NAME}-droplet gateway watchdog-check'"

unset _ENV_FILE _SCRIPT_DIR _REPO_ROOT _SSH_DROPLET
