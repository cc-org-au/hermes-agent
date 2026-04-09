# shellcheck shell=bash
# Hermes workstation helpers — source from ~/.zshrc / ~/.bashrc or via direnv (.envrc).
#
# Sets HERMES_AGENT_REPO (default: directory containing scripts/shell/ — the git checkout).
#
#   hermes …           — run repo Hermes CLI (scripts/core/hermes → venv python -m hermes_cli.main)
#   hermes … droplet   — VPS hop: run that Hermes command on the server (trailing "droplet" only;
#                        see AGENTS.md). Example: hermes doctor droplet
#
#   droplet            — interactive SSH session as hermesuser (admin hop + sudo — ssh_droplet_user.sh)
#   droplet cmd …      — run one remote command as hermesuser (same path; args become bash -lc on server)
#
#   droplet_direct     — SSH as hermesuser@host directly (requires your key in hermesuser authorized_keys)
#   droplet_direct cmd — one-shot remote command
#
# Credentials: ~/.env/.env (SSH_PORT, SSH_USER, SSH_TAILSCALE_IP or SSH_IP) and ~/.env/.ssh_key
# Overrides: HERMES_DROPLET_ENV, SSH_KEY_FILE (see scripts/core/ssh_droplet_user.sh).

if [[ -n "${ZSH_VERSION:-}" ]]; then
  # zsh: path of this file when sourced
  _HERMES_ENV_HERE="$(cd "$(dirname "${(%):-%x}")" && pwd)"
else
  _HERMES_ENV_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
export HERMES_AGENT_REPO="${HERMES_AGENT_REPO:-$(cd "${_HERMES_ENV_HERE}/../.." && pwd)}"
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
