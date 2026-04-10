# shellcheck shell=bash
# Hermes workstation helpers — source from ~/.zshrc / ~/.bashrc or via direnv (.envrc).
#
# Export HERMES_HOME before sourcing if you keep runtime config under the checkout (e.g. ~/operator/.hermes).
#
# Sets HERMES_AGENT_REPO (default: directory containing scripts/shell/ — the git checkout).
#
#   hermes …           — run repo Hermes CLI (scripts/core/hermes → venv python -m hermes_cli.main)
#   hermes … droplet   — VPS hop: run that Hermes command on the server (trailing "droplet" only;
#                        see AGENTS.md). Example: hermes doctor droplet
#   hermes … operator  — Mac mini hop: trailing "operator" only. Example: hermes doctor operator
#
#   operator           — interactive SSH to the Mac mini (scripts/shell/operator → ssh_operator.sh)
#   droplet            — interactive SSH session as hermesuser (admin hop + sudo — ssh_droplet_user.sh)
#   droplet cmd …      — run one remote command as hermesuser (same path; args become bash -lc on server)
#
#   droplet_direct     — SSH as hermesuser@host directly (requires your key in hermesuser authorized_keys)
#   droplet_direct cmd — one-shot remote command
#
# Credentials: ~/.env/.env — droplet: SSH_* ; Mac mini: MACMINI_SSH_* (see scripts/core/ssh_operator.sh).
# Overrides: HERMES_DROPLET_ENV, HERMES_OPERATOR_ENV, SSH_KEY_FILE, MACMINI_SSH_KEY.

if [[ -n "${ZSH_VERSION:-}" ]]; then
  # zsh: path of this file when sourced
  _HERMES_ENV_HERE="$(cd "$(dirname "${(%):-%x}")" && pwd)"
else
  _HERMES_ENV_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
# Walk up from this file until we find scripts/core/hermes (works for scripts/shell/ and
# memory/core/scripts/shell/ layouts; avoids ../.. guessing a wrong checkout root).
if [[ -z "${HERMES_AGENT_REPO:-}" ]]; then
  _hr="$_HERMES_ENV_HERE"
  while [[ "$_hr" != "/" ]]; do
    if [[ -f "$_hr/scripts/core/hermes" ]] || [[ -f "$_hr/scripts/core/ssh_droplet_user.sh" ]]; then
      export HERMES_AGENT_REPO="$_hr"
      break
    fi
    _hr="$(dirname "$_hr")"
  done
  if [[ -z "${HERMES_AGENT_REPO:-}" ]]; then
    echo "hermes-env.sh: could not locate Hermes repo (scripts/core/hermes missing); falling back to ../.." >&2
    export HERMES_AGENT_REPO="$(cd "${_HERMES_ENV_HERE}/../.." && pwd)"
  fi
  unset _hr
fi
_HERMES_CORE="${HERMES_AGENT_REPO}/scripts/core"
unset _HERMES_ENV_HERE

hermes() {
  if [[ ! -d "$HERMES_AGENT_REPO" ]]; then
    echo "hermes: HERMES_AGENT_REPO is not a directory: ${HERMES_AGENT_REPO}" >&2
    return 1
  fi
  local _bin="${_HERMES_CORE}/hermes"
  if [[ -f "$_bin" ]]; then
    (cd "$HERMES_AGENT_REPO" && exec bash "$_bin" "$@")
  else
    local _py="${HERMES_AGENT_REPO}/venv/bin/python"
    if [[ ! -x "$_py" ]]; then
      echo "hermes: missing ${_bin} and ${_py} (create venv or set HERMES_AGENT_REPO)" >&2
      return 1
    fi
    (cd "$HERMES_AGENT_REPO" && exec "$_py" -m hermes_cli.main "$@")
  fi
}

operator() {
  local _w="${HERMES_AGENT_REPO}/scripts/shell/operator"
  if [[ ! -f "$_w" ]]; then
    echo "operator: missing ${_w}" >&2
    return 1
  fi
  command bash "$_w" "$@"
}

droplet() {
  local _w="${HERMES_AGENT_REPO}/scripts/shell/droplet"
  if [[ ! -f "$_w" ]]; then
    echo "droplet: missing ${_w}" >&2
    return 1
  fi
  command bash "$_w" "$@"
}

droplet_direct() {
  local _w="${HERMES_AGENT_REPO}/scripts/shell/droplet_direct"
  if [[ ! -f "$_w" ]]; then
    echo "droplet_direct: missing ${_w}" >&2
    return 1
  fi
  command bash "$_w" "$@"
}
