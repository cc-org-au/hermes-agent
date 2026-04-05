# Hermes: always use the repo venv + scripts/hermes shim (including `… droplet`).
#
# Install (zsh/bash — add to ~/.zshrc or ~/.bashrc):
#   If the clone is not $HOME/hermes-agent, set the repo root (two lines — avoids zsh export quirks):
#   HERMES_AGENT_REPO=/path/to/hermes-agent
#   export HERMES_AGENT_REPO
#   source "$HERMES_AGENT_REPO/scripts/shell/hermes-env.sh"
#
# Then `hermes`, `hermes tui droplet`, etc. run via scripts/hermes → venv python -m hermes_cli.main
# (or agent-droplet when the last argument is `droplet`). This avoids a global `hermes` on PATH
# when you are not in a direnv-enabled repo directory.
#
# `droplet` — SSH to the VPS as admin (`SSH_USER`), then `sudo` to `hermesuser` (interactive remote
# shell as hermesuser). Needs ~/.env/.env: SSH_USER, SSH_PORT, SSH_TAILSCALE_IP or SSH_IP.
#
# `droplet_direct` — one-hop `ssh hermesuser@…` (scripts/ssh_droplet_hermesuser_direct.sh). Use only
# after your pubkey is in hermesuser's ~/.ssh/authorized_keys; otherwise you get Permission denied.
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

# Remote shell as hermesuser (via admin SSH + sudo — works with typical DO/VPS key-on-root-only setups).
droplet() {
  local s="${HERMES_AGENT_REPO}/scripts/ssh_droplet_user.sh"
  if [[ ! -f "$s" ]]; then
    echo "droplet: missing $s — set HERMES_AGENT_REPO to your hermes-agent checkout" >&2
    return 127
  fi
  bash "$s" "$@"
}

# One-hop ssh hermesuser@droplet (requires pubkey in hermesuser authorized_keys).
droplet_direct() {
  local s="${HERMES_AGENT_REPO}/scripts/ssh_droplet_hermesuser_direct.sh"
  if [[ ! -f "$s" ]]; then
    echo "droplet_direct: missing $s — set HERMES_AGENT_REPO to your hermes-agent checkout" >&2
    return 127
  fi
  bash "$s" "$@"
}

# Backward-compatible name for the same path as `droplet`.
droplet_sudo() {
  droplet "$@"
}
