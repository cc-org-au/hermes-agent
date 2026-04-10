#!/bin/bash
# Run ON the Mac mini (operator account target). Enforces **sudo -v** on every SSH session before
# running a shell or SSH_ORIGINAL_COMMAND (rsync, git over ssh, etc.). Install with sudo to
# /usr/local/libexec/hermes/ and point sshd **ForceCommand** (or **authorized_keys command=**) here.
#
# Prerequisites:
#   - **operator** must be in **sudoers** (e.g. macOS **Admin** group: `sudo dseditgroup -o edit -a operator -t user admin`)
#   - After editing sshd, restart Remote Login / sshd (macOS varies; see AGENTS.md)
#
# Automation without sudo gate: use a **second** SSH key in authorized_keys **without** this
# ForceCommand, restricted with **from="100.x.x.x"** (Tailscale) only.
#
# shellcheck shell=bash
set -u

_GATE_NAME="operator_ssh_gate_remote.sh"

# Attach stdin/stdout to the session TTY so sudo can prompt.
exec >/dev/tty 2>&1 || true
exec </dev/tty || true

sudo -k 2>/dev/null || true
if ! sudo -v; then
  printf '%s: sudo -v failed — add user to Admin/sudoers, then reconnect.\n' "$_GATE_NAME" >&2
  exit 1
fi

_REPO="${HERMES_OPERATOR_REPO:-${HOME}/hermes-agent}"

_run_venv_hint() {
  if [[ ! -f "${_REPO}/venv/bin/python" ]]; then
    printf '%s: no venv at %s/venv — run: cd %s && python3 -m venv venv && ./venv/bin/pip install -e .\n' \
      "$_GATE_NAME" "$_REPO" "$_REPO" >&2
  fi
}

if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
  # Non-interactive: rsync, scp, one-shot remote command.
  exec bash -lc "$SSH_ORIGINAL_COMMAND"
fi

# Interactive login session
_run_venv_hint
if [[ -d "$_REPO" ]]; then
  cd "$_REPO" || true
  if [[ -f "${_REPO}/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    . "${_REPO}/venv/bin/activate"
    export VIRTUAL_ENV="${_REPO}/venv"
    export PATH="${VIRTUAL_ENV}/bin:${PATH}"
  fi
fi
exec bash -l
