# Hermes: always use the repo venv + scripts/hermes shim (including `… droplet`).
#
# Install (zsh/bash — add to ~/.zshrc or ~/.bashrc):
#   export HERMES_AGENT_REPO="$HOME/hermes-agent"   # optional if not default
#   source "$HERMES_AGENT_REPO/scripts/shell/hermes-env.sh"
#
# Then `hermes`, `hermes tui droplet`, etc. run via scripts/hermes → venv python -m hermes_cli.main
# (or agent-droplet when the last argument is `droplet`). This avoids a global `hermes` on PATH
# when you are not in a direnv-enabled repo directory.
#
# `droplet` — interactive SSH as hermesuser on the VPS (wraps scripts/ssh_droplet_user.sh; requires
# ~/.env/.env with SSH_* and ~/.env/.ssh_key). Optional args: same as ssh_droplet_user.sh, e.g.
#   droplet 'hostname'
#
# direnv users: `.envrc` already PATH_add scripts; you can still source this file so `hermes`
# works from any cwd.

: "${HERMES_AGENT_REPO:=${HOME}/hermes-agent}"
_HERMES_SHIM="${HERMES_AGENT_REPO}/scripts/hermes"

hermes() {
  if [[ ! -x "${HERMES_AGENT_REPO}/venv/bin/python" ]]; then
    echo "hermes: missing ${HERMES_AGENT_REPO}/venv/bin/python — create venv: cd ${HERMES_AGENT_REPO} && python3 -m venv venv && ./venv/bin/pip install -e ." >&2
    return 127
  fi
  if [[ ! -x "$_HERMES_SHIM" ]]; then
    echo "hermes: missing $_HERMES_SHIM — set HERMES_AGENT_REPO to your checkout" >&2
    return 127
  fi
  command "$_HERMES_SHIM" "$@"
}

# Log into the droplet as hermesuser (from workstation). Not for use *on* the VPS.
droplet() {
  local s="${HERMES_AGENT_REPO}/scripts/ssh_droplet_user.sh"
  if [[ ! -f "$s" ]]; then
    echo "droplet: missing $s — set HERMES_AGENT_REPO to your hermes-agent checkout" >&2
    return 127
  fi
  bash "$s" "$@"
}
